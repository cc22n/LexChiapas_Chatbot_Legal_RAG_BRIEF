# LexChiapas_Grounding_Gate_Estructurado.md

Prompt para la siguiente sesion de Claude Code. Contexto: el gate de
negacion por regex en `app/rag/grounding.py` ya mostro ser fragil (el LLM
frasea rechazos de formas variadas: "no aparece ninguna disposicion",
"no se encuentra informacion", "no encontre informacion" - ensanchar el
patron se evaluo y se descarto a proposito porque tambien atraparia el
caso de proteccion animal, que si tiene contenido legitimo). Se decidio
reemplazar el heuristico de texto por un campo estructurado.

---

## Tarea 1: found_answer estructurado (reemplaza el gate por regex)

- [ ] Modificar el system prompt / schema de generacion (donde sea que se
      arma `response_json`) para que el LLM devuelva explicitamente un
      campo booleano `found_answer: true/false` junto con la respuesta,
      en vez de inferirlo despues por texto libre `[Subagente: logic]`
- [ ] Retirar (o dejar como fallback de ultimo recurso, documentado como
      tal) el heuristico de regex de `app/rag/grounding.py` una vez que
      el campo estructurado este integrado en `rag_pipeline.py`
      `[Subagente: logic]`
- [ ] Confirmar que el schema de structured output es compatible con los
      5 proveedores del fallback de LLM (NVIDIA, OpenAI, Gemini, Groq,
      y los que apliquen de Grok/DeepSeek) - no asumir que todos
      soportan el mismo formato de structured output/function calling
      sin verificarlo `[Subagente: logic]`
- [ ] Correr el golden dataset completo (24 preguntas) con NVIDIA
      deshabilitado a proposito, forzando el fallback a cada proveedor
      restante al menos una vez, para confirmar que `found_answer` se
      puebla correctamente sin importar quien genero la respuesta - esto
      es lo que el gate de regex nunca alcanzo a probar
      `[Subagente: logic]` + `[Subagente: bugs]` si algo falla

## Tarea 2: corregir expectativa del golden dataset (Adopcion Art.8)

- [ ] El sistema responde legitimamente con Codigo Civil en vez de
      Art.8 (mas detalle: edad 25, diferencia de 17 anios), y gana
      incluso con el reranker real. Esto no es un bug de codigo, es una
      expectativa de test desactualizada. Actualizar la respuesta
      esperada en el golden dataset para aceptar Codigo Civil (o ambos)
      como validos `[Subagente: logic]`

## Tarea 3: reportar el conteo real actualizado

- [ ] Correr el golden dataset completo despues de las Tareas 1 y 2, y
      reportar el desglose real passed/xfailed/failed - no asumir que
      solo queda Art. 1576 (sucesion, ya documentado como limitacion de
      calidad de embedding pendiente de fix caro con re-embed) - podria
      haber cambiado con el campo estructurado nuevo `[Subagente: logic]`

---
Algo más que sí revisaría: el caso "incompleto vs. no fundamentado" (Art.1573) como test permanente
Cuando cazaron el bug del clasificador (v1 confundía "respuesta incompleta" con "no fundamentada", degradando el caso de sucesión), lo corrigieron bien — pero por lo que reportaron, parece que quedó como bug corregido, no como caso nuevo en el golden dataset. Es justo el tipo de bug sutil que puede volver a colarse si alguien ajusta el prompt del clasificador en el futuro, y hoy nada lo protegería. Pregúntale:

"¿El caso de Art.1573 (respuesta del mismo tema pero incompleta, que debe seguir grounded=True) ya quedó como un test explícito en test_rag_regression.py, o solo se verificó a mano durante el debugging de esta sesión? Si no está como test, agrégalo — es la regresión más fácil de reintroducir sin darse cuenta."
## Nota

Art. 1576 (sucesion intestada) queda fuera de este documento a proposito
- ya esta diagnosticado y documentado en `PLAN.md` Fase 3.7 como
limitacion conocida (posicion #233 de 6,757 tras la mejor expansion de
consulta barata posible; requiere prefijo de contexto + re-embed, no
mas ajuste de consulta). No repetir ese trabajo aqui.
