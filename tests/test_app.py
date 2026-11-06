import importlib
import io
import os
import tempfile
import unittest
from PIL import Image

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['BIO_DATA_DIR'] = cls.tmp.name
        os.environ['SANDSTORM'] = '1'
        cls.module = importlib.import_module('app')
        cls.module.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        with self.client.session_transaction() as s:
            s['csrf'] = 'test-token'
        self.headers = {'X-Sandstorm-Permissions': 'edit'}

    def test_render(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'READ ONLY', r.data)

    def test_permissions_and_csrf(self):
        self.assertEqual(self.client.post('/save', data={'csrf': 'test-token'}).status_code, 403)
        self.assertEqual(self.client.post('/save', headers=self.headers).status_code, 400)

    def test_save_conflict_and_escaping(self):
        revision = self.module.load()['revision']
        data = {'csrf':'test-token', 'revision': str(revision), 'name':'<script>alert(1)</script>', 'rank':'Commander'}
        self.assertEqual(self.client.post('/save', data=data, headers=self.headers).status_code,302)
        self.assertEqual(self.module.load()['character']['rank'], 'Commander')
        self.assertIn(b'&lt;script&gt;', self.client.get('/').data)
        self.assertEqual(self.client.post('/save', data=data, headers=self.headers).status_code,409)
        self.assertEqual(self.client.get('/export').mimetype, 'application/json')

    def test_upload_and_delete(self):
        image = io.BytesIO()
        Image.new('RGB',(20,30),'orange').save(image,format='PNG')
        image.seek(0)
        r = self.client.post('/images', headers=self.headers, data={'csrf':'test-token','photo':(image,'../../portrait.png'),'caption':'Portrait'})
        self.assertEqual(r.status_code,302)
        filename = self.module.load()['images'][-1]['filename']
        self.assertNotIn('..',filename)
        self.assertEqual(self.client.get('/images/'+filename).mimetype,'image/jpeg')
        self.assertEqual(self.client.post('/images/'+filename+'/delete',headers=self.headers,data={'csrf':'test-token'}).status_code,302)
        self.assertEqual(self.client.get('/images/'+filename).status_code,404)

    def test_fake_image(self):
        r = self.client.post('/images',headers=self.headers,data={'csrf':'test-token','photo':(io.BytesIO(b'not an image'),'fake.jpg')})
        self.assertEqual(r.status_code,400)

if __name__ == '__main__':
    unittest.main()
