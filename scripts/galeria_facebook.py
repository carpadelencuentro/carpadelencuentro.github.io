"""Galería de fotos de la app: copia todas las fotos de la página de Facebook de la Carpa a fotos/galeria/fb/ y
arma galeria.json, que es lo que lee la app. Corre sola cada hora (.github/workflows/galeria-facebook.yml): lo que
se sube a Facebook aparece en la app sin tocar nada, y lo que se borra de Facebook se borra también acá.

Necesita el secreto FB_PAGE_TOKEN del repositorio: un token de la página de Facebook (permisos pages_show_list y
pages_read_engagement) sacado de un token de usuario extendido, así no vence. Sin el secreto no hace nada.
Cada foto se guarda en dos tamaños que ya da Facebook: la grande (1080 de ancho) y la miniatura para la grilla."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://graph.facebook.com/v21.0/'
TOKEN = os.environ.get('FB_PAGE_TOKEN', '').strip()
CARPETA = 'fotos/galeria/fb'
GALERIA = 'galeria.json'
# Las fotos de perfil y de portada no van a la galería.
SALTEAR = {'profile', 'cover'}
# Los álbumes automáticos de Facebook, con un nombre en español.
NOMBRES = {'wall': 'Publicaciones', 'mobile': 'Desde el celular'}


def pedir(url):
    """GET a Facebook. Si Facebook dice que no (token vencido, sin permiso), se corta todo sin tocar la galería."""
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                cuerpo = e.read().decode('utf-8', 'replace')
                sys.exit(f'Facebook respondió {e.code}: {cuerpo[:400]}')
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(5)
    sys.exit('No se pudo hablar con Facebook. Se prueba de nuevo en la próxima hora.')


def todos(ruta, **params):
    """Todas las páginas de una lista de Facebook."""
    params['access_token'] = TOKEN
    j = pedir(API + ruta + '?' + urllib.parse.urlencode(params))
    while True:
        yield from j.get('data', [])
        siguiente = j.get('paging', {}).get('next')
        if not siguiente:
            return
        j = pedir(siguiente)


def elegir(imagenes, ancho):
    """La versión más chica que tenga al menos [ancho] de ancho (o la más grande, si ninguna llega)."""
    xs = sorted(imagenes, key=lambda i: i['width'])
    for i in xs:
        if i['width'] >= ancho:
            return i['source']
    return xs[-1]['source']


def bajar(url, ruta):
    if os.path.exists(ruta):
        return
    with urllib.request.urlopen(url, timeout=120) as r:
        datos = r.read()
    with open(ruta, 'wb') as f:
        f.write(datos)


def cuantas_habia():
    try:
        with open(GALERIA, encoding='utf-8') as f:
            return sum(len(a.get('fotos', [])) for a in json.load(f).get('albumes', []))
    except (OSError, ValueError):
        return 0


def main():
    if not TOKEN:
        print('Falta el secreto FB_PAGE_TOKEN: la galería no se actualiza.')
        return
    os.makedirs(CARPETA, exist_ok=True)
    albumes, usadas = [], set()
    for a in todos('me/albums', fields='id,name,type', limit=50):
        if a.get('type') in SALTEAR:
            continue
        fotos = []
        for p in todos(f"{a['id']}/photos", fields='id,images,created_time', limit=100):
            imagenes = [i for i in p.get('images', []) if i.get('source') and i.get('width')]
            if not imagenes:
                continue
            base = f"{CARPETA}/{p['id']}"
            try:
                bajar(elegir(imagenes, 1080), base + '.jpg')
                bajar(elegir(imagenes, 360), base + '-m.jpg')
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print('No se pudo bajar la foto', p['id'], e)
                continue
            usadas.update({base + '.jpg', base + '-m.jpg'})
            fotos.append((p.get('created_time', ''), {'f': base + '.jpg', 'm': base + '-m.jpg'}))
        if not fotos:
            continue
        # Las más nuevas primero (la primera es la portada del álbum).
        fotos.sort(key=lambda x: x[0], reverse=True)
        titulo = NOMBRES.get(a.get('type'), '') or str(a.get('name', '')).strip() or 'Fotos'
        albumes.append((fotos[0][0], {'id': 'fb-' + a['id'], 'titulo': titulo[:60], 'fotos': [f for _, f in fotos]}))
    total = sum(len(a['fotos']) for _, a in albumes)
    # Si Facebook devolvió todo vacío de golpe (por ejemplo, el token perdió el permiso), no se borra la galería.
    if total == 0 and cuantas_habia() > 0:
        sys.exit('Facebook no devolvió ninguna foto: se deja la galería como estaba. Revisá el token FB_PAGE_TOKEN.')
    # Los álbumes con fotos más nuevas, primero.
    albumes.sort(key=lambda x: x[0], reverse=True)
    # Lo que se borró de Facebook se borra también acá.
    for n in os.listdir(CARPETA):
        ruta = f'{CARPETA}/{n}'
        if ruta not in usadas:
            os.remove(ruta)
    with open(GALERIA, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'albumes': [a for _, a in albumes]}, f, ensure_ascii=False, indent=1)
    print(f'{len(albumes)} álbumes, {total} fotos.')


if __name__ == '__main__':
    main()
