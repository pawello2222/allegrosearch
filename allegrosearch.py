import json
import os
import smtplib
import requests
import webbrowser
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from requests.auth import HTTPBasicAuth


class AllegroSearch:
    def __init__(self):
        self.dirname = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(self.dirname, 'config.json')) as file:
            self.config = json.load(file)

        try:
            with open(os.path.join(self.dirname, 'token.json')) as file:
                self.token = json.load(file)
            self.token = self.refresh_token()
            if 'error' in self.token:
                self.token = self.sign_in()
        except (FileNotFoundError, KeyError):
            self.token = self.sign_in()

    def get_access_code(self):
        auth_url = f"{self.config['oauth_url']}/authorize" \
                   f"?response_type=code" \
                   f"&client_id={self.config['client_id']}" \
                   f"&redirect_uri={self.config['redirect_uri']}"

        parsed_redirect_uri = requests.utils.urlparse(self.config['redirect_uri'])
        server_address = parsed_redirect_uri.hostname, parsed_redirect_uri.port

        class AllegroAuthHandler(BaseHTTPRequestHandler):
            def __init__(self, request, address, server):
                super().__init__(request, address, server)

            def do_GET(self):
                self.send_response(200, 'OK')
                self.send_header('Content-Type', 'text/html')
                self.end_headers()

                self.server.path = self.path
                self.server.access_code = self.path.rsplit('?code=', 1)[-1]

        webbrowser.open(auth_url)

        httpd = HTTPServer(server_address, AllegroAuthHandler)
        print('User authorization in progress...')

        httpd.handle_request()
        httpd.server_close()
        return httpd.access_code

    def sign_in(self):
        print("Signing in...")
        token_url = f"{self.config['oauth_url']}/token"

        access_token_data = {'grant_type': 'authorization_code',
                             'code': self.get_access_code(),
                             'redirect_uri': self.config['redirect_uri']}

        response = requests.post(url=token_url,
                                 auth=HTTPBasicAuth(self.config['client_id'], self.config['client_secret']),
                                 data=access_token_data)
        with open(os.path.join(self.dirname, 'token.json'), 'w') as file:
            json.dump(response.json(), file)
        return response.json()

    def refresh_token(self):
        print("Refreshing token...")
        token_url = f"{self.config['oauth_url']}/token"

        access_token_data = {'grant_type': 'refresh_token',
                             'refresh_token': self.token['refresh_token'],
                             'redirect_uri': self.config['redirect_uri']}

        response = requests.post(url=token_url,
                                 auth=HTTPBasicAuth(self.config['client_id'], self.config['client_secret']),
                                 data=access_token_data)
        with open(os.path.join(self.dirname, 'token.json'), 'w') as file:
            json.dump(response.json(), file)
        return response.json()

    def send_request(self, url, params):
        headers = {'charset': 'utf-8',
                   'Accept-Language': 'pl-PL',
                   'Content-Type': 'application/json',
                   'Accept': 'application/vnd.allegro.public.v1+json',
                   'Authorization': f"Bearer {self.token['access_token']}"}

        with requests.Session() as session:
            session.headers.update(headers)
            response = session.get(self.config['api_url'] + url, params=params)
            return response.json()

    def start_request(self, name):
        print(f"Sending request '{name}'...")
        with open(os.path.join(self.dirname, 'requests', name, 'params.json')) as file:
            request_config = json.load(file)
        result = self.send_request(request_config['url'], request_config['params'])
        new_items = result['items']['promoted'] + result['items']['regular']

        try:
            with open(os.path.join(self.dirname, 'requests', name, 'items.json')) as file:
                old_items = json.load(file)
        except FileNotFoundError:
            old_items = []

        unique_new_items = self.compare_items(old_items, new_items)
        self.dump_new_items(name, new_items)

        if unique_new_items:
            def item_to_send(item):
                return {'id': item['id'],
                        'name': item['name'],
                        'price': item['sellingMode']['price']['amount'],
                        'currency': item['sellingMode']['price']['currency'],
                        'format': item['sellingMode']['format']}

            items_to_send = list(map(item_to_send, unique_new_items))
            title = f"[ALLEGRO] Request: '{name}'"
            message = json.dumps(items_to_send, indent=1)
            # self.send_email(title, message)

    def start(self):
        with open(os.path.join(self.dirname, 'active.json')) as file:
            active_requests = json.load(file)

        for request in active_requests:
            self.start_request(request)

    @staticmethod
    def compare_items(old_items, new_items):
        unique_new_items = []
        for item in new_items:
            if item['id'] not in old_items:
                unique_new_items.append(item)
        return unique_new_items

    def dump_new_items(self, name, new_items):
        new_items_ids = list(map(lambda item: item['id'], new_items))
        with open(os.path.join(self.dirname, 'requests', name, 'items.json'), 'w') as file:
            json.dump(new_items_ids, file)

    def send_email(self, title, message):
        print(f"Sending email '{title}'...")
        server = smtplib.SMTP(self.config['email_server_host'], self.config['email_server_port'])
        server.starttls()
        server.login(self.config['email_sender_address'], self.config['email_sender_password'])

        msg = MIMEText(message)
        msg['Subject'] = title
        msg['From'] = self.config['email_sender_address']
        msg['To'] = self.config['email_receiver_address']

        server.sendmail(self.config['email_sender_address'], self.config['email_receiver_address'], msg.as_string())
        server.quit()


if __name__ == "__main__":
    AllegroSearch().start()
