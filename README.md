# Reto Idonia + Recog

Solución para el I Hackathon IABiomed, reto Idonia + Recog: interoperabilidad de imagen médica con Idonia y humanización del informe mediante Recog.

## Memoria técnica

La descripción completa de la solución, su arquitectura y su implementación está disponible en la [memoria técnica del proyecto](./memoria-tecnica.pdf).

El proyecto implementa:

- Fase 1: ingesta de los ficheros DICOM del estudio y del informe original en Idonia.
- Fase 2: descarga del informe original desde Idonia, humanización con Recog y subida del informe humanizado a Idonia.
- Fase 3: generación de Magic Link con QR y PIN para entrega.
- Demo visual local con Streamlit para mostrar evidencia del flujo completo.

## Arquitectura

```text
src/
  config.py                Carga segura de .env y validación de settings
  idonia_client.py         Cliente HTTP y JWT HS256 para endpoints Idonia
  pipeline_utils.py        Utilidades comunes de trazabilidad y evidencias
  ingestion_pipeline.py    Orquestación de Fase 1 y evidencias
  recog_client.py          Cliente HTTP para Recog
  humanization_pipeline.py Orquestación de Fase 2 y evidencias
  delivery_pipeline.py     Orquestación de Fase 3 y evidencias
  logger.py                Configuración de logging
  models.py                Modelos de caso, pasos y evidencias
  main.py                  CLI principal
scripts/
  test_whoami.py           Diagnóstico aislado de autenticación Idonia
  upload_report.py         Diagnóstico aislado de subida de informe
  upload_study.py          Diagnóstico aislado de subida de estudio
  get_document.py          Diagnóstico aislado de obtención de documento
  test_magic_link.py       Diagnóstico aislado de Magic Link
demo/
  app.py                   Interfaz Streamlit
  phase_runner.py          Ejecución directa de fases y captura de logs
  ui_utils.py              Componentes visuales ligeros
```

## Instalación

Requisitos:

- Python 3.10+

Instala dependencias:

```bash
pip install -r requirements.txt
```

Dependencias principales:

- `requests`: cliente HTTP para Idonia y Recog.
- `PyJWT`: firma JWT HS256 para Idonia.
- `python-dotenv`: carga de `.env`.
- `pydantic>=2`: modelos y validación de configuración/evidencias.
- `pypdf`: extracción y validación de texto en PDFs.
- `qrcode`: generación del QR ASCII en Fase 3.
- `streamlit`: demo visual local para mostrar el flujo.

## Configuración

1. Crea el archivo `.env` a partir del ejemplo:

```bash
cp .env.example .env
```

En PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Rellena credenciales y destinos de API:

- `IDONIA_BASE_URL`: entorno de Idonia Connect Cloud.
- `IDONIA_API_KEY` y `IDONIA_API_SECRET`: credenciales Idonia.
- `IDONIA_DICOM_DESTINATION`: destino para estudios DICOM.
- `IDONIA_REPORT_DESTINATION`: destino para informes.
- `IDONIA_MAGIC_LINK_ID`: identificador del visor Idonia.
- `RECOG_BASE_URL` y `RECOG_API_KEY`: configuración de Recog.

3. Prepara los archivos locales de Fase 1:

- `STUDY_FILE_PATH` debe apuntar a una carpeta con las instancias DICOM del estudio, por ejemplo `data/input/estudio`.
- `REPORT_FILE_PATH` debe apuntar al PDF del informe original, por ejemplo `data/input/informe_original.pdf`.
- `HUMANIZED_REPORT_FILE_PATH` indica dónde se guardará el PDF humanizado generado por Recog, por ejemplo `data/output/informe_explicativo_paciente.pdf`.

4. Define los datos del caso clínico:

- `PATIENT_DNI`: valor enviado a Idonia como `DICOMPatientID`.
- `CASE_ACCESSION_NUMBER`: valor enviado como `DICOMAccessionNumber`.
- `CASE_STUDY_DESCRIPTION`: valor enviado como `DICOMStudyDescription`.

Según el manual de Idonia, la ruta se construye como:

```text
<DICOMPatientID>/<DICOMAccessionNumber>/<DICOMStudyDescription>
```

En este proyecto se traduce a:

```text
PATIENT_DNI/CASE_ACCESSION_NUMBER/CASE_STUDY_DESCRIPTION
```

Con el `.env.example`, la ruta sería:

```text
12345678X/Traslados desde Asturias/RM de Rodilla Picos de Europa
```

La Fase 2 descarga el informe original desde Idonia usando la ruta exacta del documento:

```text
PATIENT_DNI/CASE_ACCESSION_NUMBER/CASE_STUDY_DESCRIPTION/<nombre del PDF original>
```

La Fase 3 genera el Magic Link sobre la ruta de entrega:

```text
PATIENT_DNI/CASE_ACCESSION_NUMBER
```

5. Configura la password adicional de Magic Link solo si se quiere doble factor:

- Si `IDONIA_MAGIC_LINK_PASSWORD` tiene valor, se envía hasheada según el manual de Idonia.
- Si `IDONIA_MAGIC_LINK_PASSWORD` está vacía, el Magic Link se crea solo con URL + PIN.

## Ejecución principal

La CLI principal usa `.env` como fuente de verdad. No requiere parámetros adicionales:

```bash
python -m src.main phase1
python -m src.main phase2
python -m src.main phase3
```

## Demo visual con Streamlit

La demo visual es una capa local de presentación sobre las mismas fases del pipeline.

Dependencias:

```bash
pip install -r requirements.txt
```

Ejecutar la app:

```bash
streamlit run demo/app.py
```

La interfaz muestra:

- Visión general del caso.
- Configuración no sensible y checks locales de rutas, DICOMs y PDFs.
- Fase 1 con diagrama, botón de ejecución real, logs y JSON de evidencia.
- Fase 2 con diagrama, logs, evidencia y comparación del PDF original frente al PDF humanizado.
- Fase 3 con Magic Link, PIN en pantalla, QR visual, logs y evidencia.
- Pantalla final con últimas evidencias y artefactos generados.

## Scripts de diagnóstico

Prueba de autenticación Idonia:

```bash
python scripts/test_whoami.py
```

Pruebas aisladas:

```bash
python scripts/upload_report.py
python scripts/upload_study.py
python scripts/get_document.py
python scripts/test_magic_link.py
```

Estos scripts están pensados para diagnóstico manual, no como dependencia del pipeline final.

## Evidencias

Las evidencias son archivos JSON técnicos que documentan cada ejecución del pipeline. Sirven para auditoría, defensa técnica y depuración sin guardar secretos ni texto clínico completo.

Incluyen:

- fase ejecutada y estado final;
- timestamps;
- pasos ejecutados y resultado de cada paso;
- rutas técnicas usadas en Idonia;
- UUIDs devueltos por Idonia;
- resumen del PDF generado por Recog;
- errores sanitizados si una fase falla.

Se generan automáticamente al ejecutar cada fase:

```text
evidence/logs/phase1_<timestamp>.json
evidence/logs/phase2_<timestamp>.json
evidence/logs/phase3_<timestamp>.json
```

## Seguridad

El proyecto incorpora varias medidas de seguridad desde la implementación:

- Las credenciales se cargan desde `.env` y no están hardcodeadas.
- `.env` queda excluido por `.gitignore`.
- `data/input/**`, `data/output/**` y `evidence/logs/**` quedan ignorados para evitar subir DICOMs, PDFs, outputs o evidencias reales.
- Las credenciales se modelan con `SecretStr` en configuración.
- Los clientes API centralizan errores sin imprimir API keys, API secrets ni JWT.
- Las evidencias se sanitizan antes de guardarse.
