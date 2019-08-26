DEPLOY_ARGS=botleague-liaison-app.yaml --quiet

logs:
	gcloud app logs tail -s botleague-liaison

deploy: test
	gcloud app deploy $(DEPLOY_ARGS)

fresh_deploy:
	gcloud beta app deploy $(DEPLOY_ARGS) --no-cache

dispath_deploy:
	gcloud app deploy dispatch.yaml

test:
	python run_tests.py
