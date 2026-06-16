"""End-to-end tests for GeoAnalysis Agent.

Usage: pytest tests/ -v
Requires: PostgreSQL + PostGIS with data loaded, ChromaDB knowledge base built.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRAG:
    """Test the RAG knowledge base layer."""

    def test_query_expansion(self):
        from src.rag.query_rewriter import expand_query
        result = expand_query("医疗设施")
        assert "诊所" in result or "clinic" in result or "health" in result

    def test_chunk_structure(self):
        from src.rag.chunker import chunk_report, DIMENSIONS
        report = {
            "sa2_code": "119011358",
            "sa2_name": "Parramatta",
            "sa4_name": "Sydney - Parramatta",
            "report": "Test report",
            "metadata": {
                "final_score": 0.38,
                "z_business": 0.1,
                "z_stops": -0.5,
                "z_schools": 0.2,
                "z_poi": -1.2,
                "rank_overall": 87,
                "median_income": 50000.0,
            },
        }
        chunks = chunk_report(report)
        assert len(chunks) == len(DIMENSIONS)
        for chunk in chunks:
            assert "text" in chunk
            assert "metadata" in chunk
            assert "suburb_name" in chunk["metadata"]
            assert "dimension" in chunk["metadata"]

    def test_chunk_metadata_has_required_fields(self):
        from src.rag.chunker import chunk_report
        report = {
            "sa2_code": "119011358",
            "sa2_name": "Test Area",
            "sa4_name": "Test SA4",
            "report": "Test",
            "metadata": {
                "final_score": 0.5,
                "z_business": 0.0,
                "z_stops": 0.0,
                "z_schools": 0.0,
                "z_poi": 0.0,
                "rank_overall": 50,
                "median_income": 50000.0,
            },
        }
        chunks = chunk_report(report)
        required_fields = ["suburb_name", "sa2_code", "sa4_name", "dimension", "z_score", "final_score"]
        for chunk in chunks:
            for field in required_fields:
                assert field in chunk["metadata"], f"Missing field: {field}"


class TestTools:
    """Test that @tool functions are importable and have correct signatures."""

    def test_import_tools(self):
        from src.tools.resource_gap_detector import resource_gap_detector
        from src.tools.spatial_accessibility import spatial_accessibility_analyzer
        from src.tools.recommendation_generator import recommendation_generator
        from src.tools.search_suburb_report import search_suburb_report
        # All should be smolagents Tool objects
        assert resource_gap_detector is not None
        assert spatial_accessibility_analyzer is not None
        assert recommendation_generator is not None
        assert search_suburb_report is not None

    def test_recommendation_input_validation(self):
        from src.tools.recommendation_generator import recommendation_generator
        result = recommendation_generator({})
        assert "error" in result

        result = recommendation_generator({"gaps": []})
        assert "recommendations" in result

    def test_recommendation_with_data(self):
        from src.tools.recommendation_generator import recommendation_generator
        gap_data = {
            "gaps": [
                {
                    "suburb": "Test Area",
                    "final_score": 0.1,
                    "z_scores": {
                        "商业活力": -1.5,
                        "交通可达性": -0.3,
                        "教育覆盖": 0.5,
                        "公共服务": -2.0,
                    },
                    "weakest_dimension": "公共服务",
                }
            ]
        }
        result = recommendation_generator(gap_data, focus="公共服务优化")
        assert len(result["recommendations"]) > 0
        assert result["recommendations"][0]["dimension"] == "公共服务"


class TestEval:
    """Test the evaluation checks."""

    def test_source_trace_check(self):
        from src.eval.final_answer_checks import check_has_source_trace
        # Should pass: has source references
        assert check_has_source_trace(
            "Parramatta 的 RAI 评分为 0.38，Z-Score 为 -0.5。数据来源：well_resourced_scores 表。"
        )
        # Should pass: short answer
        assert check_has_source_trace("请提供具体的区域名称。")
        # Should fail: long answer with no source
        assert not check_has_source_trace(
            "Parramatta 是一个很好的区域，有很多设施，居民生活便利。交通也很方便，"
            "学校质量很好，商业繁荣。总的来说这个区域各方面都很优秀，值得推荐。" * 2
        )

    def test_hallucination_check(self):
        from src.eval.final_answer_checks import check_no_hallucinated_numbers
        # Should pass
        assert check_no_hallucinated_numbers("RAI 指数为 0.38，排名第 87。")
        # Should fail: impossible RAI score
        assert not check_no_hallucinated_numbers("RAI 指数为 1.5，排名第 50。")
        # Should fail: impossible rank
        assert not check_no_hallucinated_numbers("RAI 指数为 0.5，排名第 200。")


class TestConfig:
    """Test configuration loading."""

    def test_load_config(self):
        from src.config import load_config
        config = load_config()
        assert "llm" in config
        assert "database" in config
        assert "chromadb" in config
        assert "rag" in config
        assert "agent" in config

    def test_get_llm_config(self):
        from src.config import load_config, get_llm_config
        config = load_config()
        llm = get_llm_config(config)
        assert "model_id" in llm
        assert "api_key" in llm
