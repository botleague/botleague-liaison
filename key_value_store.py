from __future__ import print_function

import os

IS_APP_ENGINE = 'IS_APP_ENGINE' in os.environ


def get_key_value_store():
    if IS_APP_ENGINE:
        return SimpleKeyValueStoreFirestore()
    else:
        return SimpleKeyValueStoreLocal()


class SimpleKeyValueStoreFirestore(object):
    def __init__(self):
        self.collection_name = 'simple_key_value_store'
        from firebase_admin import firestore
        self.kv = firestore.client().collection(self.collection_name)

    def get(self, key):
        value = self.kv.document(key).get().to_dict()[key]
        return value

    def set(self, key, value):
        self.kv.document(key).set({key: value})


class SimpleKeyValueStoreLocal(object):
    def __init__(self):
        self.kv = {}

    def get(self, key):
        return self.kv[key]

    def set(self, key, value):
        self.kv[key] = value
