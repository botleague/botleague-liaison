# Botleague Liaison

GAE app that consumes github hooks, triggers Botleague evaluations, 
and handles their results

## Run tests

pytest tests/*

## Running locally

! Don't install PyCharm's App Engine support ! Just run it as a normal Python project.

```
python main.py
``` 

```
~/bin/ngrok http 8888
```

Test hooks within https://github.com/botleague/botleague/settings/hooks


1. Change the [ngrok webook](https://github.com/botleague/botleague/settings/hooks/101461445) Payload URL to your new ngrok address
2. Use the **Recent Deliveries** to replay a hook and debug locally


## Deploy

```
gcloud app deploy
```
