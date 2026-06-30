.PHONY: install demo test api eval train frontend

install:
	pip install -r requirements.txt

demo:
	python demo.py

test:
	python -m pytest -q

api:
	uvicorn api.main:app --reload

eval:
	python -m eval.ragas_eval
	python -m finetuning.evaluate

train:
	python -m finetuning.train

frontend:
	cd frontend && npm install && npm run dev
