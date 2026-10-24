"""Control media Library: access, type sniffing, size limits, delete, playlist order, CSRF. Storage is the in-memory test one."""
import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from control.models import MediaAsset, Playlist, PlaylistItem
from control.tests.test_control import HOST, ControlTestCase, person

MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 200  # ID3 header (size 0), then a real frame header
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
        self.assertEqual((r.json()["title"], r.json()["tags"]), ("Calm", ["music", "spa", "x"]))  # audio always carries "music"
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


WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 40
AAC = b"\xff\xf1\x50\x80" + b"\x00" * 100
OGG = b"OggS" + b"\x00" * 100
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 100
M4A = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A mp42" + b"\x00" * 100
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200


class LibraryV2Tests(ControlTestCase):
    """The v2 Library UI needs: one list of types, brief messages, total size, peaks and posters, artist, timings, used in."""

    def setUp(self):
        self.admin = person("Admin", is_staff=True)
        self.client = client_for(self.admin)

    def test_types_are_the_brief_list_and_messages_match(self):
        for content, name in ((AAC, "a.aac"), (OGG, "a.ogg")):
            r = upload(self.client, content, name=name)
            self.assertEqual(r.status_code, 415, name)
            self.assertEqual(r.json()["error"], "This type can't be used. For music use MP3, M4A or WAV.")
        r = upload(self.client, HEIC, name="photo.jpg")
        self.assertEqual(r.status_code, 415)
        self.assertIn("HEIC pictures can't be shown on screens", r.json()["error"])
        for content, name in ((WAV, "a.wav"), (M4A, "a.m4a"), (MP3, "a.mp3")):
            self.assertEqual(upload(self.client, content, name=name).status_code, 201, name)
        with override_settings(CONTROL_MAX_VIDEO_MB=1):
            big = MP4 + b"\x00" * 1_048_576
            r = upload(self.client, big, name="v.mp4")
            self.assertEqual(r.status_code, 413)
            self.assertEqual(r.json()["error"], "This file is 1 MB. Videos can be up to 1 MB.")

    def test_library_total_size_is_enforced(self):
        self.assertEqual(upload(self.client, MP3).status_code, 201)
        with override_settings(CONTROL_LIBRARY_MAX_GB=0.0000001):
            r = upload(self.client, MP3, name="b.mp3")
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["error"], "The Library is full. Delete something to make room.")
        listing = self.client.get("/library/assets/").json()
        self.assertEqual(listing["library"]["used_bytes"], len(MP3))
        self.assertGreater(listing["library"]["max_bytes"], 1_000_000_000)

    def test_default_tags_by_kind_and_the_tag_rules(self):
        upload(self.client, MP3)
        upload(self.client, PNG, name="p.png")
        audio, image = MediaAsset.objects.get(kind="audio"), MediaAsset.objects.get(kind="image")
        self.assertEqual((audio.tags, image.tags), (["music"], ["screens"]))
        r = post_json(self.client, f"/library/assets/{image.id}/update/", {"tags": ["music", "lounge"]})
        self.assertEqual(r.json()["tags"], ["screens", "lounge"])  # pictures are never music
        r = post_json(self.client, f"/library/assets/{audio.id}/update/", {"tags": []})
        self.assertEqual(r.json()["tags"], ["music"])

    def test_artist_is_for_music_only(self):
        upload(self.client, MP3)
        upload(self.client, PNG, name="p.png")
        audio, image = MediaAsset.objects.get(kind="audio"), MediaAsset.objects.get(kind="image")
        self.assertEqual(post_json(self.client, f"/library/assets/{audio.id}/update/", {"artist": "Night Shift Quartet"}).json()["artist"], "Night Shift Quartet")
        self.assertEqual(post_json(self.client, f"/library/assets/{image.id}/update/", {"artist": "x"}).status_code, 400)

    def test_browser_measurements_peaks_and_poster(self):
        upload(self.client, MP3)
        upload(self.client, MP4, name="v.mp4")
        audio, video = MediaAsset.objects.get(kind="audio"), MediaAsset.objects.get(kind="video")
        peaks = [round(i / 20, 2) for i in range(20)]
        r = self.client.post(f"/library/assets/{audio.id}/duration/", {"duration_seconds": "200.5", "peaks": json.dumps(peaks)})
        self.assertEqual(r.json()["peaks"], peaks)
        self.assertEqual(self.client.post(f"/library/assets/{audio.id}/duration/", {"duration_seconds": "1", "peaks": "[1,2]"}).json()["peaks"], peaks)  # too short: ignored
        poster = SimpleUploadedFile("p.jpg", JPEG)
        r = self.client.post(f"/library/assets/{video.id}/duration/", {"duration_seconds": "30", "width": "1920", "height": "1080", "poster": poster})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["poster_url"])
        video.refresh_from_db()
        self.assertEqual((video.width, video.height), (1920, 1080))
        path = video.poster.name
        self.assertTrue(default_storage.exists(path))
        bad = self.client.post(f"/library/assets/{video.id}/duration/", {"duration_seconds": "30", "poster": SimpleUploadedFile("p.jpg", b"not a jpeg")})
        self.assertEqual(bad.status_code, 400)
        self.client.post(f"/library/assets/{video.id}/delete/")
        self.assertFalse(default_storage.exists(path))

    def test_picture_timing_in_a_screens_playlist(self):
        upload(self.client, PNG, name="p.png")
        upload(self.client, MP4, name="v.mp4")
        image, video = MediaAsset.objects.get(kind="image"), MediaAsset.objects.get(kind="video")
        playlist = post_json(self.client, "/library/playlists/create/", {"name": "Lounge reel", "kind": "screens"}).json()
        base = f"/library/playlists/{playlist['id']}"
        post_json(self.client, f"{base}/items/add/", {"asset_id": str(image.id)})
        added = post_json(self.client, f"{base}/items/add/", {"asset_id": str(video.id)}).json()
        image_item, video_item = added["items"][0]["id"], added["items"][1]["id"]
        self.assertIsNone(added["items"][0]["seconds"])
        r = post_json(self.client, f"{base}/items/seconds/", {"item_id": image_item, "seconds": 12})
        self.assertEqual(r.json()["items"][0]["seconds"], 12)
        for body in ({"item_id": image_item, "seconds": 3}, {"item_id": image_item, "seconds": 61}, {"item_id": image_item, "seconds": "x"}, {"item_id": video_item, "seconds": 8}):
            self.assertEqual(post_json(self.client, f"{base}/items/seconds/", body).status_code, 400, body)

    def test_used_in_lists_playlists(self):
        upload(self.client, MP3)
        audio = MediaAsset.objects.get()
        playlist = post_json(self.client, "/library/playlists/create/", {"name": "Evening", "kind": "music"}).json()
        post_json(self.client, f"/library/playlists/{playlist['id']}/items/add/", {"asset_id": str(audio.id)})
        found = self.client.get("/library/assets/").json()["assets"][0]
        self.assertEqual(found["playlists"], [{"id": playlist["id"], "name": "Evening", "kind": "music"}])
        self.assertEqual(found["uploaded_by"], self.admin.email)

    def test_plain_form_post_works_without_javascript(self):
        r = self.client.post("/library/assets/upload/", {"file": SimpleUploadedFile("song.mp3", MP3), "next": "page"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/library/")
        self.assertEqual(MediaAsset.objects.get().title, "song")
        page = self.client.get("/library/")
        self.assertContains(page, "song")
        self.assertContains(page, "added to the Library")
        bad = self.client.post("/library/assets/upload/", {"file": SimpleUploadedFile("x.exe", b"MZ\x00\x00"), "next": "page"}, follow=True)
        self.assertContains(bad, "This type can&#x27;t be used")

    def test_library_page_has_no_demo_chip_and_says_it_is_real(self):
        page = self.client.get("/library/")
        self.assertContains(page, "Files here are stored for real.")
        self.assertNotContains(page, "ctl-chip-demo")
        html = page.content.decode()
        self.assertIn(".m4a", html)
        for gone in (".ogg", ".aac", ".heic"):
            self.assertNotIn(f'"{gone}', html)
            self.assertNotIn(f",{gone}", html)


class HardeningTests(ControlTestCase):
    def setUp(self):
        self.admin = person("Admin", is_staff=True)
        self.client = client_for(self.admin)

    def test_bad_ids_are_404_or_400_never_500(self):
        upload(self.client, MP3)
        playlist = post_json(self.client, "/library/playlists/create/", {"name": "P", "kind": "music"}).json()
        base = f"/library/playlists/{playlist['id']}/items"
        for bad in ("not-a-uuid", "", None, 12345, "x" * 500):
            r = post_json(self.client, f"{base}/add/", {"asset_id": bad})
            self.assertEqual(r.status_code, 404, bad)
            self.assertEqual(r.json()["error"], "That file is not in the Library.")
        for name in ("remove", "seconds"):
            for bad in ("9" * 40, "-1", "abc", None):
                self.assertEqual(post_json(self.client, f"{base}/{name}/", {"item_id": bad, "seconds": 5}).status_code, 404, (name, bad))
        self.assertEqual(post_json(self.client, f"{base}/reorder/", {"item_ids": ["9" * 40]}).status_code, 400)

    def test_dev_media_is_admin_only_and_limited_to_library_files(self):
        import importlib

        import config.urls_control as urls

        with override_settings(DEBUG=True):
            from django.core.files.storage import FileSystemStorage
            import tempfile
            from unittest import mock

            with tempfile.TemporaryDirectory() as root:
                (__import__("pathlib").Path(root) / "control" / "media").mkdir(parents=True)
                (__import__("pathlib").Path(root) / "control" / "media" / "a.mp3").write_bytes(MP3)
                (__import__("pathlib").Path(root) / "secret.txt").write_text("private")
                with mock.patch("django.core.files.storage.default_storage._wrapped", FileSystemStorage(location=root), create=True):
                    importlib.reload(urls)
                    view = urls.urlpatterns[-1].callback
                    from django.test import RequestFactory

                    def call(user, path):
                        request = RequestFactory().get("/media/" + path)
                        request.user = user
                        try:
                            return view(request, path).status_code
                        except Exception as error:
                            return getattr(error, "status_code", type(error).__name__)

                    self.assertEqual(call(self.admin, "control/media/a.mp3"), 200)
                    self.assertEqual(call(self.admin, "secret.txt"), "Http404")
                    self.assertEqual(call(person("Office", is_staff=True), "control/media/a.mp3"), "Http404")
        importlib.reload(urls)

    def test_quota_counts_posters_and_is_checked_under_the_lock(self):
        upload(self.client, MP4, name="v.mp4")
        asset = MediaAsset.objects.get()
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 996
        r = self.client.post(f"/library/assets/{asset.id}/duration/", {"duration_seconds": 5, "poster": SimpleUploadedFile("p.jpg", jpeg)})
        self.assertEqual(r.status_code, 200, r.content)
        asset.refresh_from_db()
        self.assertEqual(asset.poster_bytes, 1000)
        self.assertEqual(self.client.get("/library/assets/").json()["library"]["used_bytes"], len(MP4) + 1000)
        with override_settings(CONTROL_LIBRARY_MAX_GB=(len(MP4) + 1500) / 1024 ** 3):
            self.assertEqual(upload(self.client, MP3, name="b.mp3").status_code, 201)  # 1500 left, mp3 is ~214 bytes
            r = self.client.post(f"/library/assets/{asset.id}/duration/", {"duration_seconds": 5, "poster": SimpleUploadedFile("p.jpg", jpeg + b"\x00" * 2000)})
            self.assertEqual(r.status_code, 413)

    def test_media_links_get_the_long_expiry(self):
        from unittest import mock

        from control.views_library import media_url

        upload(self.client, MP3)
        asset = MediaAsset.objects.get()
        storage = mock.Mock(bucket_name="b")
        storage.url.return_value = "https://signed"
        field = mock.Mock(storage=storage, name="n")
        field.name = "control/media/x.mp3"
        with override_settings(CONTROL_MEDIA_URL_HOURS=12):
            self.assertEqual(media_url(field), "https://signed")
        storage.url.assert_called_once_with("control/media/x.mp3", expire=12 * 3600)
        self.assertEqual(self.client.get("/library/assets/").json()["library"]["url_ttl_seconds"], 12 * 3600)

    def test_sniff_is_strict(self):
        from control.media_rules import sniff

        ebml = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\x82\x84"
        self.assertEqual(sniff(ebml + b"webm" + b"\x00" * 20)[1], "webm")
        self.assertIsNone(sniff(ebml + b"\x00\x00\x00\x00" + b"matroska"))  # an mkv is not a webm
        self.assertIsNone(sniff(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"<html>garbage"))  # ID3 then no audio frame
        self.assertIsNone(sniff(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xe1\x90\x00"))  # reserved version bits
        self.assertIsNone(sniff(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\xf0\x00"))  # bitrate 1111
        self.assertEqual(sniff(MP3)[1], "mp3")
        self.assertEqual(sniff(b"\xff\xfb\x90\x00")[1], "mp3")  # a bare frame with no tag
        self.assertIsNone(sniff(b"\xff\xfb\xfc\x00"))  # sample rate bits 11
        for brand in (b"qt  ", b"3gp5", b"XXXX"):
            self.assertIsNone(sniff(b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 20), brand)
        for brand in (b"isom", b"mp41", b"mp42", b"avc1", b"M4V ", b"dash"):
            self.assertEqual(sniff(b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 20)[1], "mp4", brand)

    def test_id3_tag_larger_than_the_header_read_is_followed(self):
        tag = 6000  # syncsafe size bytes for 6000 = 0,0,0x2e,0x70
        size = bytes([0, 0, (tag >> 7) & 0x7F, tag & 0x7F])
        data = b"ID3\x03\x00\x00" + size + b"\x00" * tag + b"\xff\xfb\x90\x00" + b"\x00" * 100
        self.assertEqual(upload(self.client, data).status_code, 201)
        bad = b"ID3\x03\x00\x00" + size + b"\x00" * tag + b"<html>" + b"\x00" * 100
        self.assertEqual(upload(self.client, bad).status_code, 415)
