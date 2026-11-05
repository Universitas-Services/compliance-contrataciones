"""Pruebas sin LLM del reintento con prioridad tras un 429."""

from __future__ import annotations

import os
from unittest import mock

import httpx2
from openai import RateLimitError

from app.core import llm_client as L


def _429() -> RateLimitError:
    respuesta = httpx2.Response(429, request=httpx2.Request("POST", "http://x"))
    return RateLimitError("Resource exhausted", response=respuesta, body=None)


def _llamar(activa: str, proveedor: str, efectos: list) -> tuple[list, mock.Mock]:
    os.environ["LLM_PRIORIDAD_429"] = activa
    os.environ["LLM_PROVIDER"] = proveedor
    chat = mock.Mock(side_effect=efectos)
    with (
        mock.patch.object(L, "_chat_create", chat),
        mock.patch.object(L, "_client", return_value=None),
        mock.patch.object(L, "_model", return_value="m"),
        mock.patch.object(L.time, "sleep") as dormir,
    ):
        try:
            L._llamar_modelo_meta(system="s", user_content="u")
        except RateLimitError:
            pass
    return [c.kwargs["extra_headers"] for c in chat.call_args_list], dormir


def main() -> None:
    ok = ("texto", "stop")

    headers, dormir = _llamar("true", "vertex", [ok])
    assert headers == [None], headers
    print("OK sin 429 no usa prioridad")

    headers, dormir = _llamar("true", "vertex", [_429(), ok])
    assert headers == [None, L._HEADERS_PRIORIDAD], headers
    dormir.assert_not_called()
    print("OK primer 429: reintenta al momento con prioridad")

    headers, dormir = _llamar("true", "vertex", [_429(), _429(), ok])
    assert headers == [None, L._HEADERS_PRIORIDAD, L._HEADERS_PRIORIDAD], headers
    assert dormir.call_count == 1
    print("OK 429 con prioridad: sigue con espera creciente")

    for activa, proveedor in (("false", "vertex"), ("true", "openai")):
        headers, dormir = _llamar(activa, proveedor, [_429(), ok])
        assert headers == [None, None], headers
        assert dormir.call_count == 1
    print("OK apagada o sin Vertex: comportamiento anterior")


if __name__ == "__main__":
    main()
