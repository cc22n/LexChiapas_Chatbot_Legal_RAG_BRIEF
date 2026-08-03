# LexChiapas — Leyes pendientes de integrar (catalogo completo de Congreso)

Generado el 2026-07-20 con `ingestion/scrapers/congreso_scraper.py` (arreglado
en Fase 3.7, ver `PLAN.md`), comparado contra la tabla `documents` real
(`is_active=True`) al momento de generar este archivo. Actualizado el
2026-07-31 tras integrar un lote de 12 leyes priorizadas por utilidad real
para un ciudadano comun (procesal civil/penal, agua, asentamientos humanos,
derechos indigenas, forestal, fraccionamientos, electoral, fauna, victimas,
desaparicion de personas, discriminacion) -- ver
`ingestion/load_codigo_procedimientos_civiles.py` y los demas
`ingestion/load_*.py` de ese mismo lote (fecha 2026-07-31) para el detalle
completo de cada ingesta, incluyendo typos de PDF encontrados y corregidos.
De paso se corrigieron dos entradas de esta tabla que ya estaban integradas
desde antes pero seguian listadas como pendientes (Ley de Asistencia e
Integracion de las Personas Adultas Mayores, Ley para la Inclusion de las
Personas con Discapacidad) -- inconsistencia detectada al recalcular el
conteo real contra `documents.is_active=True`, no relacionada con el lote de
12 de esta fecha.

- **Total de leyes vigentes en el sitio de Congreso:** 146
- **Ya integradas en el corpus (documents.is_active=True):** 32 documentos
  activos en total (ver "Fuentes de datos" en `CLAUDE.md` y el detalle de
  cada uno en `PLAN.md` Fase 3.6/3.7; lote mas reciente del 2026-07-31
  documentado en los docstrings de `ingestion/load_*.py` correspondientes).
  De esos 32, **29** tienen un nombre identificable en este catalogo
  especifico de Congreso (`list_available_laws()`); los otros 3 (Ley para la
  Inclusion de las Personas con Discapacidad, Ley de Asistencia e
  Integracion de las Personas Adultas Mayores, y una tercera ley cargada
  via Consejeria Juridica como fuente alterna cuando el host de Congreso
  fallaba para esa ley especifica, ver docstrings de los `load_ley_*.py`
  correspondientes) se cargaron usando el host de Consejeria Juridica como
  fuente de descarga y no aparecen bajo ese mismo nombre exacto en el
  listado HTML de Congreso, por lo que no se restan del conteo de
  pendientes de ESTE catalogo especifico.
- **Pendientes (listadas abajo, 146 menos las 29 que si matchean por nombre
  contra este catalogo de Congreso):** 117 (conteo verificado contra las
  filas reales de las tablas de abajo, no solo aritmetica de cabecera --
  ver comando de verificacion mas abajo)

**No se ha ingerido nada de esta lista automaticamente.** Es un catalogo de
referencia para decidir que agregar despues, con revision humana caso por
caso -- ya hubo un incidente real en este proyecto (Codigo Fiscal vs. Codigo
de la Hacienda Publica, dos nombres para documentos que resultaron ser
duplicados con texto identico) que solo se detecto comparando articulos a
mano, no con un match automatico de nombres. Antes de cargar cualquier ley de
esta lista, conviene: (1) confirmar que no es un duplicado de algo ya
cargado con otro nombre, (2) revisar 3-4 chunks despues de cargarla como se
ha hecho con cada ley anterior, y (3) correr el set de regresion
(`tests/test_rag_regression.py`) para confirmar que no hay regresiones.

Para recargar/actualizar esta lista mas adelante (el sitio de Congreso
cambia con el tiempo):

```python
from ingestion.scrapers.congreso_scraper import list_available_laws
from app.database import SessionLocal
from app.models import Document
# comparar list_available_laws() contra Document.nombre (is_active=True)
```

---

## Constitucion

| Nombre | URL |
|---|---|
| CONSTITUCIÓN POLÍTICA DEL ESTADO LIBRE Y SOBERANO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0002.pdf?v=Njg= |

## Codigos

| Nombre | URL |
|---|---|
| CÓDIGO DE EJECUCIÓN DE SANCIONES PENALES Y MEDIDAS DE LIBERTAD ANTICIPADA PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0005.pdf?v=NA== |
| CÓDIGO DE ORGANIZACIÓN DEL PODER JUDICIAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0008.pdf?v=OQ== |
| CÓDIGO FISCAL MUNICIPAL | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/codigo fiscal municipal.pdf?v=Mw== |

**Nota:** Código de Procedimientos Penales y Código de Procedimientos
Civiles ya se integraron el 2026-07-31 (documents.id 30 y 29
respectivamente) para acompañar al Código Penal (ya cargado) y al Código
Civil (ya cargado) -- juntos cubren el proceso completo, no solo el derecho
sustantivo.

## Leyes (orden alfabetico, tal como aparecen en el sitio)

| Nombre | URL |
|---|---|
| DECLARATORIA DE INICIO DE FUNCIONES DEL CENTRO DE CONCILIACIÓN LABORAL DEL ESTADO DE CHIAPAS Y DE LOS JUZGADOS ESPECIALIZADOS EN MATERIA LABORAL DEL TRIBUNAL SUPERIOR DE JUSTICIA DEL PODER JUDICIAL DEL ESTADO | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0143.pdf?v=MQ== |
| DECLARATORIA DE INICIO DE VIGENCIA DEL CODIGO NACIONAL DE PROCEDIMIENTOS PENALES EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/declaratoria de inicio de vigencia del codigo nacional de procedimientos penales en el estado de chiapas.pdf?v=Mw== |
| LEY ABROGADA MEDIANTE DECRETO NUMERO 018 DE FECHA 12 DE NOVIEMBRE DE 2019. LEY DE PREVENCIÓN INTEGRAL PARA LAS COMUNIDADES SEGURAS EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0123.pdf?v=Mg== |
| LEY DE ADQUISICIONES, ARRENDAMIENTO DE BIENES MUEBLES Y LA CONTRATACIÓN DE SERVICIOS PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0016.pdf?v=MTE= |
| LEY DE ARCHIVOS DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0059.pdf?v=NA== |
| LEY DE ASOCIACIONES PÚBLICO PRIVADAS PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0052.pdf?v=NA== |
| LEY DE BIENES ASEGURADOS, ABANDONADOS Y DECOMISADOS PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0019.pdf?v=Nw== |
| LEY DE CATASTRO PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0020.pdf?v=NA== |
| LEY DE CATEGORIZACIÓN POLÍTICO-ADMINISTRATIVA DE LOS NÚCLEOS DE POBLACIÓN DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de categorizacion politico-administrativa de los nucleos de poblacion del estado de chiapas.pdf?v=Mw== |
| LEY DE CENTROS ECOTURÍSTICOS DE AUTOGESTIÓN COMUNITARIA PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de centros ecoturisticos de autogestion comunitaria para el estado de chiapas.pdf?v=Mw== |
| LEY DE CIENCIA, TECNOLOGÍA E INNOVACIÒN DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0023.pdf?v=NA== |
| LEY DE CIUDADES RURALES SUSTENTABLES PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de ciudades rurales sustentables para el estado de chiapas.pdf?v=Mg== |
| LEY DE CONCESIONES DE SERVICIOS E INFRAESTRUCTURA PÚBLICA PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0024.pdf?v=NQ== |
| LEY DE CONTROL CONSTITUCIONAL PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de control constitucional para el estado de chiapas.pdf?v=NA== |
| LEY DE COORDINACIÓN PARA EL ESTABLECIMIENTO Y DESARROLLO DE LAS ZONAS ECONÓMICAS ESPECIALES EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0127.pdf?v=MQ== |
| LEY DE DERECHOS DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0061.pdf?v=MjM= |
| LEY DE DERECHOS PARA EL EJERCICIO DEL PERIODISMO EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de derechos para el ejercicio del periodismo en el estado de chiapas.pdf?v=Mw== |
| LEY DE DESARROLLO CONSTITUCIONAL DEL CONGRESO DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0068.pdf?v=MTc= |
| LEY DE DESARROLLO CONSTITUCIONAL EN MATERIA DE GOBIERNO Y ADMINISTRACIÓN MUNICIPAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0073.pdf?v=MjQ= |
| LEY DE DESARROLLO CONSTITUCIONAL PARA LA IGUALDAD DE GÉNERO Y ACCESO A UNA VIDA LIBRE DE VIOLENCIA PARA LAS MUJERES | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0133.pdf?v=OQ== |
| LEY DE DESARROLLO ECONÓMICO Y  ATRACCIÓN DE INVERSIONES DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0076.pdf?v=NQ== |
| LEY DE DESARROLLO RURAL SUSTENTABLE DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0134.pdf?v=Mg== |
| LEY DE DESARROLLO SOCIAL Y DEL HUMANISMO DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0045.pdf?v=Ng== |
| LEY DE DESARROLLO Y PROTECCIÓN A LA ACTIVIDAD ARTESANAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0077.pdf?v=MTA= |
| LEY DE EDUCACIÓN PARA EL ESTADO LIBRE Y SOBERANO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0030.pdf?v=MjE= |
| LEY DE ENTIDADES PARAESTATALES DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de entidades paraestatales del estado de chiapas.pdf?v=Mw== |
| LEY DE ENTREGA  RECEPCIÓN DE LOS AYUNTAMIENTOS DEL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0031.pdf?v=NA== |
| LEY DE ESTABLECIMIENTOS MUTUANTES DEL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0086.pdf?v=OA== |
| LEY DE EXPROPIACIÓN DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0033.pdf?v=NA== |
| LEY DE EXTINCIÓN DE DOMINIO PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de extincion de dominio para el estado de chiapas.pdf?v=Mw== |
| LEY DE FIRMA ELECTRÓNICA AVANZADA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de firma electronica avanzada del estado de chiapas.pdf?v=Mw== |
| LEY DE FISCALIZACIÓN Y RENDICIÓN DE CUENTAS DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0036.pdf?v=MTI= |
| LEY DE FOMENTO A LAS ACTIVIDADES DE LAS ORGANIZACIONES DE LA SOCIEDAD CIVIL PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de fomento a las actividades de las organizaciones de la sociedad civil para el estado de chiapas.pdf?v=Mg== |
| LEY DE FOMENTO PARA EL USO DE LA BICICLETA Y PROTECCIÓN AL CICLISTA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0142.pdf?v=MQ== |
| LEY DE FOMENTO PARA LA LECTURA Y EL LIBRO DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0091.pdf?v=Ng== |
| LEY DE FOMENTO Y SANIDAD PECUARIA PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0040.pdf?v=Nw== |
| LEY DE FOMENTO, DESARROLLO E INNOVACIÓN PARA LA ESTRATEGIA MARCA CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0109.pdf?v=NQ== |
| LEY DE GOBIERNO DIGITAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0147.pdf?v=Mw== |
| LEY DE HACIENDA MUNICIPAL | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de hacienda municipal.pdf?v=Mw== |
| LEY DE INGRESOS PARA EL ESTADO DE CHIAPAS PARA EL EJERCICIO FISCAL 2026 | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0114.pdf?v=MjM= |
| LEY DE LA COMISIÓN ESTATAL DE LOS DERECHOS HUMANOS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0093.pdf?v=Ng== |
| LEY DE LA DEFENSORÍA PÚBLICA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de la defensoria publica del estado de chiapas.pdf?v=Mw== |
| LEY DE LA JUVENTUD PARA EL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de la juventud para el estado de chiapas..pdf?v=Mg== |
| LEY DE LAS CULTURAS Y LAS ARTES DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de las culturas y las artes del estado de chiapas.pdf?v=Mg== |
| LEY DE MECANISMOS ALTERNATIVOS DE SOLUCIÓN DE CONTROVERSIAS PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0043.pdf?v=Nw== |
| LEY DE MEDIOS DE IMPUGNACIÓN EN MATERIA ELECTORAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0137.pdf?v=NQ== |
| LEY DE MEJORA REGULATORIA PARA EL ESTADO Y LOS MUNICIPIOS DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0122.pdf?v=Mg== |
| LEY DE MUNICIPALIZACIÓN PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0129.pdf?v=MQ== |
| LEY DE OBRA PUBLICA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0044.pdf?v=MTE= |
| LEY DE PARTICIPACIÓN CIUDADANA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0139.pdf?v=Mw== |
| LEY DE PESCA Y ACUACULTURA SUSTENTABLE PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0090.pdf?v=Mw== |
| LEY DE PLANEACIÓN PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0046.pdf?v=NQ== |
| LEY DE PRESUPUESTO, CONTABILIDAD Y GASTO PUBLICO MUNICIPAL | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0047.pdf?v=NQ== |
| LEY DE PROCEDIMIENTOS ADMINISTRATIVOS PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0048.pdf?v=NA== |
| LEY DE PROPIEDAD EN CONDOMINIO DE INMUEBLES PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0087.pdf?v=Mw== |
| LEY DE PROTECCIÓN CONTRA LA EXPOSICIÓN AL HUMO DE TABACO DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0125.pdf?v=Mw== |
| LEY DE PROTECCIÓN DE DATOS PERSONALES EN POSESIÓN DE SUJETOS OBLIGADOS DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0135.pdf?v=NA== |
| LEY DE PROTECCIÓN DE MONUMENTOS Y SITIOS DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de proteccion de monumentos y sitios del estado de chiapas.pdf?v=Mg== |
| LEY DE RESIDUOS SÓLIDOS PARA EL ESTADO DE CHIAPAS Y SUS MUNICIPIOS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0083.pdf?v=Nw== |
| LEY DE RESPONSABILIDAD PATRIMONIAL DEL ESTADO DE CHIAPAS Y SUS MUNICIPIOS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0146.pdf?v=MQ== |
| LEY DE RESPONSABILIDADES ADMINISTRATIVAS PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0131.pdf?v=NQ== |
| LEY DE SEGURIDAD PRIVADA PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de seguridad privada para el estado de chiapas.pdf?v=Mg== |
| LEY DE TURISMO PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0075.pdf?v=OA== |
| LEY DE VALUACIÓN PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley de valuacion para el estado de chiapas.pdf?v=NQ== |
| LEY DE VOLUNTAD ANTICIPADA PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0149.pdf?v=NA== |
| LEY DEL COLEGIO DE BACHILLERES DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0056.pdf?v=NQ== |
| LEY DEL ESCUDO Y EL HIMNO DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0013.pdf?v=Nw== |
| LEY DEL FOMENTO AL DEPORTE DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley del fomento al deporte del estado de chiapas.pdf?v=NA== |
| LEY DEL FOMENTO Y DESARROLLO AGRÍCOLA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley del fomento y desarrollo agricola del estado de chiapas.pdf?v=Mg== |
| LEY DEL INSTITUTO DE SEGURIDAD SOCIAL DE LOS TRABAJADORES DEL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0105.pdf?v=Nw== |
| LEY DEL PATRIMONIO DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0074.pdf?v=Nw== |
| LEY DEL SISTEMA ANTICORRUPCIÓN DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0128.pdf?v=Mw== |
| LEY DEL SISTEMA ESTATAL DE CULTURA FÍSICA Y DEPORTE PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley del sistema estatal de cultura fisica y deporte para el estado de chiapas.pdf?v=Mg== |
| LEY DEL SISTEMA ESTATAL DE SEGURIDAD PÚBLICA | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0060.pdf?v=OQ== |
| LEY ESTATAL DEL PERIÓDICO OFICIAL | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0130.pdf?v=MQ== |
| LEY ESTATAL PARA EL DIALOGO, LA CONCILIACIÓN Y LA PAZ DIGNA EN CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley estatal para el dialogo, la conciliacion y la paz digna en chiapas.pdf?v=Mg== |
| LEY ESTATAL PARA LA PREVENCIÓN SOCIAL DE LA VIOLENCIA Y LA DELINCUENCIA | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0126.pdf?v=MQ== |
| LEY ORGÁNICA DE LA ADMINISTRACIÓN PÚBLICA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0065.pdf?v=Mzc= |
| LEY ORGÁNICA DE LA BENEMÉRITA UNIVERSIDAD AUTÓNOMA DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0066.pdf?v=NQ== |
| LEY ORGÁNICA DE LA FISCALÍA GENERAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0120.pdf?v=Ng== |
| LEY ORGÁNICA DE LA UNIVERSIDAD AUTÓNOMA DE CIENCIAS Y ARTES DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0067.pdf?v=NA== |
| LEY ORGÁNICA DEL CENTRO DE CONCILIACIÓN LABORAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0140.pdf?v=Mg== |
| LEY ORGÁNICA DEL CONSEJO ESTATAL PARA LAS CULTURAS Y LAS ARTES DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0069.pdf?v=Nw== |
| LEY ORGÁNICA DEL INSTITUTO CASA DE LAS ARTESANÍAS DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0070.pdf?v=NA== |
| LEY ORGANICA DEL INSTITUTO DE BOMBEROS DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0015.pdf?v=MTE= |
| LEY ORGÁNICA DEL INSTITUTO DE SALUD | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley organica del instituto de salud.pdf?v=Mg== |
| LEY ORGÁNICA DEL SISTEMA MUNICIPAL DE AGUA POTABLE Y ALCANTARILLADO | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley organica del sistema municipal de agua potable y alcantarillado.pdf?v=Mg== |
| LEY ORGÁNICA DEL TRIBUNAL  DE JUSTICIA ADMINISTRATIVA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0132.pdf?v=Nw== |
| LEY PARA EL EJERCICIO PROFESIONAL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley para el ejercicio profesional del estado de chiapas.pdf?v=Mg== |
| LEY PARA EL FOMENTO Y REGULACIÓN DE PRODUCTOS ORGÁNICOS DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley para el fomento y regulacion de productos organicos del estado de chiapas.pdf?v=Mg== |
| LEY PARA LA ADAPTACIÓN Y MITIGACIÓN ANTE EL CAMBIO CLIMÁTICO EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0097.pdf?v=Mw== |
| LEY PARA LA ATENCIÓN DE PERSONAS CON TRASTORNOS DEL ESPECTRO AUTISTA PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0053.pdf?v=OQ== |
| LEY PARA LA ATENCIÓN Y PROTECCIÓN A LOS DERECHOS DE LAS PERSONAS EN CONTEXTO DE MOVILIDAD HUMANA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0148.pdf?v=Mg== |
| LEY PARA LA GESTIÓN INTEGRAL DEL RIESGO DE DESASTRES Y PROTECCIÓN CIVIL DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0049.pdf?v=OQ== |
| LEY PARA LA PREVENCIÓN Y ATENCIÓN DEL DESPLAZAMIENTO INTERNO EN EL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0100.pdf?v=Ng== |
| LEY PARA LA PREVENCIÓN, TRATAMIENTO Y CONTROL DE LA DIABETES EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0136.pdf?v=MQ== |
| LEY PARA LA PROTECCIÓN A PERSONAS QUE INTERVIENEN EN EL PROCEDIMIENTO PENAL EN EL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley para la proteccion a personas que intervienen en el procedimiento penal en el estado de chiapas..pdf?v=Mg== |
| LEY PARA PREVENIR Y COMBATIR LA TRATA DE PERSONAS EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0144.pdf?v=MQ== |
| LEY PARA PREVENIR Y COMBATIR LA TRATA DE PERSONAS EN EL ESTADO DE CHIAPAS (2) | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0141.pdf?v=MQ== |
| LEY QUE CREA EL FONDO PARA EL DESARROLLO Y MEJORA DE LA PROCURACIÓN DE JUSTICIA DEL ESTADO | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley que crea el fondo para el desarrollo y mejora de la procuracion de justicia del estado.pdf?v=NA== |
| LEY QUE CREA EL INSTITUTO DEL CAFÉ DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0082.pdf?v=OA== |
| LEY QUE CREA LA COMISIÓN ESTATAL DE CONCILIACIÓN Y ARBITRAJE MEDICO DEL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0098.pdf?v=Mw== |
| LEY QUE ESTABLECE EL PROCESO DE ENTREGA RECEPCIÓN DE LA ADMINISTRACIÓN PÚBLICA DEL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0124.pdf?v=Mw== |
| LEY QUE ESTABLECE LAS BASES DE OPERACIÓN DE LA SECRETARIA DE SEGURIDAD DEL PUEBLO DEL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0064.pdf?v=MTg= |
| LEY QUE ESTABLECE LAS BASES NORMATIVAS PARA LA EXPEDICIÓN DE LOS REGLAMENTOS DE CONSTRUCCIÓN EN EL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley que establece las bases normativas para la expedicion de los reglamentos de construccion en el estado de chiapas..pdf?v=Mg== |
| LEY QUE ESTABLECE LOS LINEAMIENTOS EN EL DESARROLLO DE LA OBRA PUBLICA PARA EL CUMPLIMIENTO DE LOS OBJETIVOS DE DESARROLLO DE MILENIO PARA EL ESTADO Y MUNICIPIOS DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley que establece los lineamientos en el desarrollo de la obra publica para el cumplimiento de los objetivos de desarrollo de milenio para el estado y municipios de chiapas.pdf?v=Mg== |
| LEY QUE REGULA EL ASEGURAMIENTO, ADMINISTRACIÓN, ENAJENACIÓN Y DISPOSICIÓN FINAL DE VEHÍCULOS AUTOMOTORES, ACCESORIOS O COMPONENTES ABANDONADOS PARA EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0108.pdf?v=NQ== |
| LEY QUE REGULA LA PRESTACIÓN DE SERVICIOS PARA LA ATENCIÓN, CUIDADO Y DESARROLLO INTEGRAL INFANTIL EN EL ESTADO DE CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0094.pdf?v=Ng== |
| LEY REGLAMENTARIA DEL ARTÍCULO 40 DE LA CONSTITUCIÓN POLITICA DEL ESTADO DE CHIAPAS, QUE FIJA LAS BASES PARA LA TOMA DE PROTESTA DEL GOBERNADOR ELECTO. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley reglamentaria del articulo 40 de la constitucion politica del estado de chiapas, que fija las bases para la toma de protesta del gobernador electo..pdf?v=Mg== |
| LEY SOBRE INSTALACIÓN DE ANUNCIOS U OBRAS CON FINES DE PUBLICIDAD EN LAS CARRETERAS DEL ESTADO | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/ley sobre instalacion de anuncios u obras con fines de publicidad en las carreteras del estado.pdf?v=Mw== |

**Nota:** "LEY PARA PREVENIR Y COMBATIR LA TRATA DE PERSONAS..." aparece DOS
VECES en el sitio con URLs distintas (`LEY_0144` y `LEY_0141`) -- revisar
cual es la version vigente antes de cargar, probablemente una reemplazo a
la otra.

## Presupuesto, reglamentos y otros

| Nombre | URL |
|---|---|
| PRESUPUESTO DE EGRESOS DEL ESTADO DE CHIAPAS PARA EL EJERCICIO FISCAL 2026 | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0115.pdf?v=MjY= |
| REGLAMENTO DEL CONSEJO DE PARTICIPACIÓN DE VÍCTIMAS DE LA COMISIÓN DE SEGUIMIENTO A LAS ACCIONES DE PROCURACIÓN DE JUSTICIA VINCULADAS A LOS FEMINICIDIOS EN CHIAPAS | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0151.pdf?v=MQ== |
| REGLAMENTO DE TRANSPARENCIA,  ACCESO A LA INFORMACIÓN Y PROTECCIÓN DE DATOS PERSONALES DEL HONORABLE CONGRESO  DEL ESTADO DE CHIAPAS. | https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0117.pdf?v=Ng== |

**Nota:** Ley de Ingresos y Presupuesto de Egresos son documentos anuales
("...PARA EL EJERCICIO FISCAL 2026") -- si se cargan, van a quedar
obsoletos cada año; requieren un proceso de actualizacion distinto al resto
del corpus (leyes que cambian por reforma, no por calendario).
