# Botleague Liaison

GAE app that consumes github hooks, triggers Botleague evaluations, 
and handles their results

For info on the API, flow, etc.. see the [botleague docs](https://github.com/botleague/botleague)

## Run tests

pytest -v tests/*

## Running locally

! Don't install PyCharm's App Engine support ! Just run it as a normal Python project.

```
python main.py
``` 

```
~/bin/ngrok http 8888
```

Or if you want to test problem endpoint locally as well, you can add the 
following to your `~/.ngrok2/ngrok.yml`

```
authtoken: your-auth-token


tunnels:
  bll:
    proto: http
    addr: 8888
  problem-endpoint:
    proto: http
    addr: 8000
```

Then run this to start both 

```
ngrok start bll problem-endpoint
```

Test hooks within https://github.com/botleague/botleague/settings/hooks


1. Change the [ngrok webook](https://github.com/botleague/botleague/settings/hooks/101461445) Payload URL to your new ngrok address
2. Use the **Recent Deliveries** to replay a hook and debug locally



## Deploy, logs, etc..

See Makefile

## Disabling git hooks

In case of a fire, you may want to disable initiation of any evals. You can 
do so by setting `DISABLE_GIT_HOOK_CONSUMPTION=true` in Firestore. 


## Botleague submodule

This is meant to be a readonly copy of botleague for more efficient 
fetching of files without using the GitHub API. Checking it in is okay, but
not necessary as the server will pull latest for things like problem ci's.
