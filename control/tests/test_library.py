"""Control media Library: access, type sniffing, size limits, delete, playlist order, CSRF. Storage is the in-memory test one."""
import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from control.models import MediaAsset, Playlist, PlaylistItem
from control.tests.test_control import HOST, ControlTestCase, person

MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (640).to_bytes(4, "big") + (480).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00" + b"\x00" * 50
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"avc1" + b"\x00" * 100
HEVC = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"hvc1" + b"\x00" * 100


def client_for(user, csrf=False):
    client = Client(HTTP_HOST=HOST, enforce_csrf_checks=csrf)
    client.force_login(user)
    return client


def upload(client, content, name="a.mp3", **extra):
    return client.post("/library/assets/upload/", {"file": SimpleUploadedFile(name, content), **extra})


def post_json(client, path, body):
    return client.post(path, json.dumps(body), content_type="application/json")


class LibraryTests(ControlTestCase):
    def setUp(self):
        self.admin = person("Admin", is_staff=True)
        self.client = client_for(self.admin)

    def test_access_matrix(self):
        office = person("Office", is_staff=True)
        for path in ("/library/", "/library/assets/", "/library/playlists/"):
            self.assertEqual(client_for(office).get(path).status_code, 404, path)
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(upload(client_for(office), MP3).status_code, 404)
        self.assertEqual(Client(HTTP_HOST=HOST).get("/library/assets/").status_code, 302)

    def test_upload_stores_by_uuid_and_lists_with_filters(self):
        response = upload(self.client, MP3, name="../../evil name.mp3", tags="Music, chill!")
        self.assertEqual(response.status_code, 201, response.content)
        asset = MediaAsset.objects.get()
        self.assertEqual((asset.kind, asset.mime, asset.title, asset.tags, asset.uploaded_by), ("audio", "audio/mpeg", "evil name", ["music", "chill"], self.admin))
        self.assertEqual(asset.file.name, f"control/media/{asset.id}.mp3")
        self.assertTrue(default_storage.exists(asset.file.name))
        upload(self.client, PNG, name="p.png")
        image = MediaAsset.objects.get(kind="image")
        self.assertEqual((image.width, image.height), (640, 480))
        kinds = lambda q: [a["kind"] for a in self.client.get("/library/assets/" + q).json()["assets"]]
        self.assertEqual(kinds("?kind=image"), ["image"])
        self.assertEqual(kinds("?tag=music"), ["audio"])
        self.assertEqual(len(kinds("")), 2)

    def test_type_is_sniffed_not_trusted(self):
        for content, name in ((b"<html><script>alert(1)</script></html>", "song.mp3"), (b"MZ\x90\x00" + b"\x00" * 50, "x.png"), (HEVC, "v.mp4")):
            response = upload(self.client, content, name=name)
            self.assertIn(response.status_code, (415,), name)
            self.assertIn("error", response.json())
        self.assertEqual(MediaAsset.objects.count(), 0)
        self.assertEqual(upload(self.client, MP4, name="clip.mp4").status_code, 201)  # right bytes, any name

    def test_size_limits_per_kind(self):
        with override_settings(CONTROL_MAX_AUDIO_MB=0, CONTROL_MAX_IMAGE_MB=0, CONTROL_MAX_VIDEO_MB=1):
            self.assertEqual(upload(self.client, MP3).status_code, 413)
            self.assertEqual(upload(self.client, PNG, name="p.png").status_code, 413)
            self.assertEqual(upload(self.client, MP4 + b"\x00" * 1_048_576, name="v.mp4").status_code, 413)
            self.assertEqual(upload(self.client, MP4, name="v.mp4").status_code, 201)

    def test_rename_tag_duration_and_delete_removes_the_file(self):
        upload(self.client, MP3)
        asset = MediaAsset.objects.get()
        path = asset.file.name
        r = post_json(self.client, f"/library/assets/{asset.id}/update/", {"title": "Calm", "tags": ["Spa", "spa", "x"]})
        self.assertEqual((r.json()["title"], r.json()["tags"]), ("Calm", ["spa", "x"]))
        self.assertEqual(post_json(self.client, f"/library/assets/{asset.id}/duration/", {"duration_seconds": 185.4}).json()["duration_seconds"], 185.4)
        self.assertEqual(post_json(self.client, f"/library/assets/{asset.id}/duration/", {"duration_seconds": "nope"}).status_code, 400)
        self.assertEqual(self.client.get(f"/library/assets/{asset.id}/delete/").status_code, 405)
        self.assertEqual(self.client.post(f"/library/assets/{asset.id}/delete/").status_code, 200)
        self.assertFalse(MediaAsset.objects.exists())
        self.assertFalse(default_storage.exists(path))

    def test_csrf_is_required_for_writes(self):
        strict = client_for(self.admin, csrf=True)
        self.assertEqual(upload(strict, MP3).status_code, 403)
        self.assertEqual(strict.post("/library/playlists/create/", {"name": "x", "kind": "music"}).status_code, 403)
        self.assertEqual(MediaAsset.objects.count() + Playlist.objects.count(), 0)

    def test_playlists_reorder_keeps_positions_unique(self):
        ids = []
        for i in range(3):
            upload(self.client, MP3, title=f"t{i}")
        assets = list(MediaAsset.objects.order_by("title"))
        playlist = post_json(self.client, "/library/playlists/create/", {"name": "Evening", "kind": "music"}).json()
        base = f"/library/playlists/{playlist['id']}"
        for asset in assets:
            self.assertEqual(post_json(self.client, f"{base}/items/add/", {"asset_id": str(asset.id)}).status_code, 201)
        ids = [i["id"] for i in self.client.get("/library/playlists/").json()["playlists"][0]["items"]]
        new = [ids[2], ids[0], ids[1]]
        r = post_json(self.client, f"{base}/items/reorder/", {"item_ids": new})
        self.assertEqual([(i["id"], i["position"]) for i in r.json()["items"]], list(zip(new, (1, 2, 3))))
        self.assertEqual(post_json(self.client, f"{base}/items/reorder/", {"item_ids": new[:2]}).status_code, 400)
        r = post_json(self.client, f"{base}/items/remove/", {"item_id": new[0]})
        self.assertEqual([i["position"] for i in r.json()["items"]], [1, 2])
        # a screens playlist refuses audio, and deleting a playlist keeps the files
        screens = post_json(self.client, "/library/playlists/create/", {"name": "Lounge", "kind": "screens"}).json()
        self.assertEqual(post_json(self.client, f"/library/playlists/{screens['id']}/items/add/", {"asset_id": str(assets[0].id)}).status_code, 400)
        self.client.post(f"{base}/delete/")
        self.assertEqual((Playlist.objects.count(), PlaylistItem.objects.count(), MediaAsset.objects.count()), (1, 0, 3))
