from pathlib import Path

import pytest

from jarvis_dev.projects import ProjectError, ProjectService, project_slug, validate_name


@pytest.mark.parametrize("name", ["../fora", "C:\\fora", "/tmp/fora", "a/b", "CON", "a?b", "..", "a\n"])
def test_rejects_unsafe_names(name):
    with pytest.raises(ProjectError):
        validate_name(name)


def test_normalizes_portuguese_name():
    assert project_slug("análise de vendas") == "analise-de-vendas"


def test_create_never_overwrites_existing_folder(tmp_path: Path):
    service = ProjectService(tmp_path)
    folder = tmp_path / "calculadora"
    folder.mkdir()
    marker = folder / "keep.txt"
    marker.write_text("preservado", encoding="utf-8")
    with pytest.raises(ProjectError, match="já existe"):
        service.create_python_project("calculadora", "operações básicas", lambda _: None)
    assert marker.read_text(encoding="utf-8") == "preservado"


def test_create_generates_files_and_reports_steps(tmp_path: Path, monkeypatch):
    service = ProjectService(tmp_path)
    steps = []

    class Completed:
        returncode = 0

    def fake_run(*args, **kwargs):
        (tmp_path / "calculadora" / ".venv").mkdir()
        return Completed()

    monkeypatch.setattr("jarvis_dev.projects.subprocess.run", fake_run)
    monkeypatch.setattr(ProjectService, "_launch_code", staticmethod(lambda _: (True, None)))
    result = service.create_python_project("calculadora", "operações básicas", steps.append)
    assert result["created"] and result["venv_created"] and result["vscode_opened"]
    assert set(result["files_created"]) == {"main.py", "README.md", ".gitignore", "requirements.txt"}
    assert "def calcular" in (tmp_path / "calculadora" / "main.py").read_text(encoding="utf-8")
    assert any("ambiente virtual" in step for step in steps)


def test_venv_failure_preserves_generated_files(tmp_path: Path, monkeypatch):
    service = ProjectService(tmp_path)

    class Failed:
        returncode = 1

    monkeypatch.setattr("jarvis_dev.projects.subprocess.run", lambda *args, **kwargs: Failed())
    monkeypatch.setattr(ProjectService, "_launch_code", staticmethod(lambda _: (False, "VS Code indisponível")))
    result = service.create_python_project("teste", "exemplo", lambda _: None)
    assert result["created"] and not result["venv_created"]
    assert (tmp_path / "teste" / "main.py").exists()
    assert len(result["errors"]) == 2


def test_refuses_symlinked_project(tmp_path: Path):
    service = ProjectService(tmp_path / "allowed")
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (service.root / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Este ambiente não permite criar links simbólicos")
    with pytest.raises(ProjectError, match="simbólicos"):
        service.inspect_project("link", lambda _: None)


def test_inspection_omits_credentials(tmp_path: Path):
    service = ProjectService(tmp_path)
    project = tmp_path / "demo"
    project.mkdir()
    (project / ".env").write_text("PRIVATE=do-not-send", encoding="utf-8")
    (project / "main.py").write_text("OPENROUTER_API_KEY = 'not-sk-format'\nprint('ok')\n", encoding="utf-8")
    result = service.inspect_project("demo", lambda _: None)
    assert ".env" not in result["files"]
    assert "not-sk-format" not in result["files"]["main.py"]
    assert "print('ok')" in result["files"]["main.py"]
