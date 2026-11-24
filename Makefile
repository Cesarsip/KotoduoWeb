# Kotoduo Produccion - tareas comunes (Informe 3, seccion 8.2)
PYTHON ?= python

.PHONY: test run health verificar clean

test:
	$(PYTHON) datos/preparar_semilla.py
	$(PYTHON) datos/ejecutar_datos.py
	$(PYTHON) datos/crear_documentos.py
	$(PYTHON) -m pytest api/ -q

run:
	cd api && uvicorn app:app --host 127.0.0.1 --port 8000 --reload

health:
	curl -s http://127.0.0.1:8000/health

verificar:
	bash despliegue/scripts/verificar.sh http://127.0.0.1:8000

clean:
	rm -f datos/kotoduo.db datos/documentos.json
	rm -f api/.pytest_cache -r
