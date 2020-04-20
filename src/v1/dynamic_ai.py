import requests
import time

SIMILAR = 5
UNSIMILAR = 10

class DynamicAI(object):
    _ENDPOINT_URL = "https://isaas-prod.gcp.dyn-ai.com/api"
    _MAX_LIFETIME = 86400

    def __init__(self, auth_token, endpoint_url=None):
        self._endpoint = endpoint_url if endpoint_url else self.__class__._ENDPOINT_URL
        self._auth_token = auth_token
        self._messages = dict()
        self._categories = dict()
        self._checkpoint = dict()

    def _api_call(self, body):
        headers = {
            "Authorization": "Bearer %s" %(self._auth_token)
        }
        response = requests.post(self._endpoint, headers=headers, json=body)
        #print(" => Response({}): {}".format(response.status_code, response.text))
        #print(response.headers)
        return response.json()

    def start(self, max_lifetime = 0):
        if not max_lifetime:
            max_lifetime = self.__class__._MAX_LIFETIME
        response = self._api_call({"type":"startVM", "maxLifetime":max_lifetime})
        return bool(response['result'] == 'success')

    def shutdown(self):
        response = self._api_call({"type":"killVM"})
        self._messages.clear()
        self._categories.clear()
        self._checkpoint.clear()

    def is_ready(self):
        response = self._api_call({"type":"isReady"})
        return bool(response['ready'])

    def reset(self):
        self._api_call({"type":"reset"})
        self._messages.clear()
        self._categories.clear()
        self._checkpoint.clear()

    def create_checkpoint(self):
        response = self._api_call({"type":"saveCheckpoint"})
        if response['result'] == 'success':
            self._checkpoint['time'] = time.time()
            self._checkpoint['messages'] = dict(_messages)
            self._checkpoint['categories'] = dict(_categories)
            return True
        return False

    def restore_checkpoint(self):
        if not self._checkpoint:
            raise RuntimeError('To respore checkpoint, you should create it first')

        response = self._api_call({"type":"restoreCheckpoint"})
        if response['result'] == 'success':
            _messages = dict(self._checkpoint['messages'])
            _categories = dict(self._checkpoint['categories'])
            return True
        return False

    def add_message(self, message):
        attempt = 0
        max_attempts = 10
        while True:
            try:
                response = self._api_call(
                    {
                        "type": "addMessage",
                        "message": message,
                        "security_group": "default"
                    })

                message_id = response.get('message_id')
                if type(message_id) == str and len(message_id) > 0:
                    self._messages[message_id] = message
                    return message_id;
                return None
            except:
                attempt += 1
                if attempt == max_attempts:
                    raise

    def add_feedback(self, message_id, relations):
        if message_id not in self._messages:
            raise ValueError('Unknown message_id')

        rel = []
        for id, flags in relations:
            rel.append({'id': id, 'flags': flags})

        response = self._api_call(
            {
                "type": "addFeedback",
                "message_id": message_id,
                "relations": rel
            })        
        return response.get('result') == 'success'

    def set_category(self, message_id, category):
        if message_id not in self._messages:
            raise ValueError('Unknown message_id')

        relations = list()
        for id, cat in self._categories.items():
            if id == message_id:
                continue
            if cat == category:
                relations.append((id, SIMILAR))
            else:
                relations.append((id, UNSIMILAR))

        self._categories[message_id] = category;
        return self.add_feedback(message_id, relations)

    def _extract_value(self, text, key):
        if text is None or key is None:
            return None
        x = text.split()
        for i in range(0, len(x)-2):
            if x[i] == key and x[i + 1] == '=':
                return x[i + 2]
        return None

    def _translate_similarity(self, x):
        message_id = str(x.get('internalId', ''))
        return {
            'message_id': message_id,
            'message_text': self._messages.get(message_id, ''),
            'similarity': int(self._extract_value(x.get('techReport'), 'bits')),
            'accuracy': round(float(x.get('accuracy')), 1),
            'is_approved': bool(x.get('isApproved')),
            'is_same_text': bool(x.get('theSameText')),
            'has_statistics': bool(x.get('statisticsExist'))
        }

    def get_similarity(self, message_id, accuracy_limit=0.6, block_limit=2):
        response = self._api_call(
            {
                "type": "getSimilarity",
                "message_id": message_id,
                "precision_limit": accuracy_limit,
                "block_limit": block_limit
            })
        similarity = response["similarity"]
        return [self._translate_similarity(x) for x in similarity if x.get('internalId', '') != message_id]

    def get_tech_report(self, message_id, accuracy_limit=0.6, block_limit=2):
        response = self._api_call(
            {
                "type": "getSimilarity",
                "message_id": message_id,
                "precision_limit": accuracy_limit,
                "block_limit": block_limit
            })
        return response["tech_report"]

    def predict_category(self, message_id, accuracy_limit=0.6):
        if message_id not in self._messages:
            raise ValueError('Unknown message_id')

        if message_id in self._categories:
            return {
                'category': self._categories.get(message_id),
                'accuracy': 1.0,
                'is_approved': True,
            }

        similarity = self.get_similarity(message_id, accuracy_limit)

        for s in similarity:
            id = s.get('message_id');
            if id not in self._categories:
                continue
            if s.get('similarity', 0) < 75:
                continue
            return {
                'category': self._categories.get(id),
                'accuracy': s.get('accuracy'),
                'is_approved': s.get('is_approved'),
            }

        return {
            'category': None,
            'accuracy': 0.0,
            'is_approved': False,
        }

    def list_messages(self, category=None):
        if category is None:
            return dict(self._messages)
        return {id: self._messages.get(id) for id, cat in self._categories.items() if cat == category}

    def list_categories():
        return dict(self._categories)
