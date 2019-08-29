DEPLOY_ARGS=botleague-liaison-app.yaml --quiet

logs:
	gcloud app logs tail -s botleague-liaison

deploy: test
	gcloud beta app deploy $(DEPLOY_ARGS) --no-cache

test:
	python run_tests.py
