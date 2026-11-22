from dotanalyst import parser


class FakeProcess:
    def __init__(self, args, **kwargs):
        self.args = args
        self.stopped = False

    def poll(self):
        return None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout):
        return 0


def bundled(tmp_path):
    java = tmp_path / "runtime" / "bin" / "java.exe"
    java.parent.mkdir(parents=True)
    java.touch()
    return tmp_path


def test_uses_a_parser_that_answers_already(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "answers", lambda: True)
    monkeypatch.setattr(parser.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("started")))
    assert parser.start(bundled(tmp_path)) is None


def test_runs_without_a_bundled_parser(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "answers", lambda: False)
    assert parser.start(tmp_path) is None


def test_starts_the_bundled_parser_and_waits_until_it_answers(tmp_path, monkeypatch):
    calls = iter([False, False, True])  # not up before the start, then once more, then up
    monkeypatch.setattr(parser, "answers", lambda: next(calls))
    monkeypatch.setattr(parser, "DATA", tmp_path / "data")
    monkeypatch.setattr(parser.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(parser.time, "sleep", lambda s: None)
    process = parser.start(bundled(tmp_path / "parser"))
    assert process.args[-3:] == ["-jar", tmp_path / "parser" / "parser.jar", "5600"]
    assert next(calls, "spent") == "spent"
    parser.stop(process)
    assert process.stopped
