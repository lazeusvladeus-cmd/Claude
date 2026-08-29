"""Тести CLI (main.py): парсинг команд, --dry-run, обробка помилок."""

from __future__ import annotations

import pytest

import main
from src.exceptions import AgentAuthError, AgentConfigError


@pytest.fixture(autouse=True)
def _patch_settings(mocker, settings):
    """Підміняє load_settings() на тестовий Settings, щоб не читати реальний .env."""
    mocker.patch("main.load_settings", return_value=settings)
    mocker.patch("main.setup_logging")
    return settings


class TestBuildParser:
    def test_discover_has_dry_run_flag(self) -> None:
        parser = main.build_parser()
        args = parser.parse_args(["discover", "--dry-run"])
        assert args.dry_run is True
        assert args.func is main.cmd_discover

    def test_status_command_has_no_dry_run_requirement(self) -> None:
        parser = main.build_parser()
        args = parser.parse_args(["status"])
        assert args.func is main.cmd_status

    def test_check_replies_has_watch_flag(self) -> None:
        parser = main.build_parser()
        args = parser.parse_args(["check-replies", "--watch", "--dry-run"])
        assert args.watch is True
        assert args.dry_run is True

    def test_missing_command_is_required(self) -> None:
        parser = main.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestCommandDispatch:
    def test_cmd_discover_calls_run_discovery(self, mocker) -> None:
        stats = mocker.MagicMock()
        stats.as_dict.return_value = {"leads_created": 3}
        mocker.patch("main.lead_discovery.run_discovery", return_value=stats)

        main.main(["discover", "--dry-run"])

        main.lead_discovery.run_discovery.assert_called_once()
        _, kwargs = main.lead_discovery.run_discovery.call_args
        assert kwargs["dry_run"] is True

    def test_cmd_pipeline_runs_all_four_modules_in_order(self, mocker) -> None:
        call_order = []

        def _make_stub(module_attr, label):
            stub = mocker.MagicMock()
            stub.as_dict.return_value = {}

            def _side_effect(*args, **kwargs):
                call_order.append(label)
                return stub

            return _side_effect

        mocker.patch("main.lead_discovery.run_discovery", side_effect=_make_stub(None, "discover"))
        mocker.patch("main.enrichment.run_enrichment", side_effect=_make_stub(None, "enrich"))
        mocker.patch("main.analyzer.run_analysis", side_effect=_make_stub(None, "analyze"))
        mocker.patch("main.outreach_writer.run_draft", side_effect=_make_stub(None, "draft"))

        main.main(["pipeline", "--dry-run"])

        assert call_order == ["discover", "enrich", "analyze", "draft"]

    def test_cmd_status_prints_summary(self, capsys, settings) -> None:
        from src.db import upsert_lead

        upsert_lead(settings.leads_db_path, {"place_id": "p1", "name": "Тест"})

        main.main(["status"])

        captured = capsys.readouterr()
        assert "Усього лідів: 1" in captured.out

    def test_agent_auth_error_exits_with_code_2(self, mocker, capsys) -> None:
        mocker.patch(
            "main.lead_discovery.run_discovery",
            side_effect=AgentAuthError("Токен протерміновано, потрібна повторна авторизація."),
        )

        with pytest.raises(SystemExit) as exc_info:
            main.main(["discover"])

        assert exc_info.value.code == 2
        assert "авторизац" in capsys.readouterr().out.lower()

    def test_config_error_exits_with_code_1(self, mocker, capsys) -> None:
        mocker.patch("main.load_settings", side_effect=AgentConfigError("Відсутній ключ API."))

        with pytest.raises(SystemExit) as exc_info:
            main.main(["discover"])

        assert exc_info.value.code == 1
        assert "Відсутній ключ" in capsys.readouterr().out
