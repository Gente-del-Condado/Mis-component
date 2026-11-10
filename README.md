# Mis-component

![Icono del catálogo](icon.png)

Catálogo de integraciones de Home Assistant Core para **Private Git Manager**.

## Integraciones disponibles

| Integración | Carpeta |
| --- | --- |
| Private Git Manager · Forgejo Backup | [pgm_forgejo_backup](custom_components/pgm_forgejo_backup/) |
| PiVigia | [pivigia](custom_components/pivigia/) |
| JackSignal | [jacksignal](custom_components/jacksignal/) |
| Headscale Gateway | [headscale_gateway](custom_components/headscale_gateway/) |

Los proyectos publican únicamente su integración mediante GitHub Actions en Mis-component de Forgejo. Forgejo replica el catálogo a GitHub. Para instalar aplicaciones del Supervisor, usa [Mis-app](https://github.com/Gente-del-Condado/Mis-app).

## Instalar o actualizar Forgejo Backup

1. En **Repositorios**, añade este catálogo con su URL SSH, rama `main` y una clave de despliegue de lectura. Verifica la huella del servidor y sincroniza.
2. En **Componentes**, busca **Forgejo Backup**. Pulsa **Instalar integración** o **Actualizar integración**, revisa el commit y confirma.
3. Reinicia Home Assistant Core. Para el primer uso, añade **Private Git Manager · Forgejo Backup** en **Ajustes → Dispositivos y servicios**.

Forgejo Backup necesita otro repositorio privado para almacenar las copias cifradas. La integración genera su propia clave de despliegue con escritura y mantiene el índice de copias recientes en el README que crea en ese destino.

[Instalar componentes](https://gente-del-condado.github.io/HA-Private-Git-Manager/#componentes) · [Configurar Forgejo Backup y recuperar copias](https://gente-del-condado.github.io/HA-Private-Git-Manager/#copias-forgejo)

El código se mantiene en [HA-Private-Git-Manager](https://github.com/Gente-del-Condado/HA-Private-Git-Manager). El flujo de publicación sincroniza la integración desde allí.
