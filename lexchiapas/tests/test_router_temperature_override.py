from app.config import get_ai_config
from app.llm import router
from app.llm.providers import _PROVIDER_API_KEY_ATTR


class _Recorder:
    def __init__(self):
        self.temperatures = []

    def create(self, **kwargs):
        self.temperatures.append(kwargs["temperature"])
        if len(self.temperatures) == 1:
            raise RuntimeError("primer modelo falla para forzar el siguiente")

        class _Msg:
            content = "ok"

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]
            usage = None

        return _Resp()


def test_entry_temperature_overrides_global_temperature(monkeypatch):
    config = {
        "llm": {
            "temperature": 0.1,
            "fallback_order": [
                {"provider": "nvidia_nim", "model": "a"},
                {"provider": "moonshot", "model": "kimi-k3", "temperature": 1},
            ],
        }
    }
    rec = _Recorder()
    monkeypatch.setattr(router, "get_ai_config", lambda: config)

    class _Client:
        chat = type("Chat", (), {"completions": rec})()

    monkeypatch.setattr(router, "get_client_for_provider", lambda provider, timeout=None: _Client())

    router.generate_with_fallback([{"role": "user", "content": "hola"}])

    assert rec.temperatures == [0.1, 1]  # NIM usa el global, Kimi su override


def test_moonshot_provider_is_wired_in_real_config():
    # Si falta cualquiera de las tres piezas, la entrada de Kimi fallaria al
    # construir el cliente y el router saltaria de proveedor sin avisar.
    llm = get_ai_config()["llm"]
    assert _PROVIDER_API_KEY_ATTR["moonshot"] == "kimi_api_key"
    assert llm["providers"]["moonshot"]["base_url"].startswith("https://api.moonshot.ai")
    kimi = [e for e in llm["fallback_order"] if e["provider"] == "moonshot"]
    assert kimi and all(e.get("temperature") == 1 for e in kimi)
