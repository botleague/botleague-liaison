import os

# TODO: Move this and key_value_store into shared botleague-gcp pypi package

# For local testing, set SHOULD_USE_FIRESTORE=false in your environment
SHOULD_USE_FIRESTORE = os.environ.get('SHOULD_USE_FIRESTORE', 'true') == 'true'

TOKEN_NAME = 'LEADERBOARD_GITHUB_TOKEN'
if SHOULD_USE_FIRESTORE:
    import firebase_admin
    from firebase_admin import firestore
    firebase_admin.initialize_app()
    SECRETS = firestore.client().collection('secrets')
    GITHUB_TOKEN = SECRETS.document(TOKEN_NAME).get().to_dict()['token']
else:
    # For local testing a single instance of this server
    if TOKEN_NAME not in os.environ:
        raise RuntimeError('No github token in env')
    GITHUB_TOKEN = os.environ[TOKEN_NAME]
    os.environ['should_gen_leaderboard'] = False
