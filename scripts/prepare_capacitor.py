import os
import shutil

def prepare_www():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    www_dir = os.path.join(project_root, 'www')
    os.makedirs(www_dir, exist_ok=True)

    files_to_copy = [
        ('mapa.html', 'index.html'),
        ('mapa.html', 'mapa.html'),
        ('ikonky.html', 'ikonky.html'),
        ('manifest.json', 'manifest.json'),
        ('service-worker.js', 'service-worker.js'),
        ('robots.txt', 'robots.txt'),
        ('sitemap.xml', 'sitemap.xml'),
    ]

    for src_name, dst_name in files_to_copy:
        src_path = os.path.join(project_root, src_name)
        dst_path = os.path.join(www_dir, dst_name)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
            print(f"[OK] Skopírované: {src_name} -> www/{dst_name}")

    # Copy static directory
    src_static = os.path.join(project_root, 'static')
    dst_static = os.path.join(www_dir, 'static')
    if os.path.exists(src_static):
        if os.path.exists(dst_static):
            shutil.rmtree(dst_static)
        shutil.copytree(src_static, dst_static)
        print("[OK] Zložka static skopírovaná do www/static")

    print(f"\n[ÚSPECH] Zložka www pripravená na synchronizáciu cez 'npx cap sync'!")

if __name__ == '__main__':
    prepare_www()
