# Mis-component

![Icono del catálogo](icon.png)

Catálogo de integraciones de Home Assistant Core para **Private Git Manager**.

## JackSignal

Reproductor de audio local con avisos de Alarmo, sonidos independientes al abrir/cerrar sensores, texto a voz configurable sin YAML y receptor DLNA exclusivamente de audio. Todos los avisos comparten las prioridades del reproductor.

[Guía de configuración](custom_components/jacksignal/README.md) · [Repositorio individual para HACS / Marketplace](https://github.com/Gente-del-Condado/jacksignal-ha) · [Instalador para Home Assistant OS](https://github.com/Gente-del-Condado/Mis-app/tree/main/jacksignal_installer).

Elige una sola vía de actualización de la integración. Este catálogo reúne varias integraciones; para HACS utiliza el repositorio individual enlazado.

## Integraciones disponibles

En Home Assistant 2026.11 o posterior, usa el botón de cada integración para abrir su repositorio en el Marketplace. Si se solicita, conecta GitHub, añade el repositorio como **Integración** y pulsa **Instalar**.

| Integración | Carpeta | Marketplace |
| --- | --- | --- |
| Private Git Manager · Forgejo Backup | [pgm_forgejo_backup](custom_components/pgm_forgejo_backup/) | [![Instalar Private Git Manager · Forgejo Backup desde el Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Gente-del-Condado&repository=HA-Private-Git-Manager&category=integration) |
| PiVigia | [pivigia](custom_components/pivigia/) | [![Instalar PiVigia desde el Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Gente-del-Condado&repository=pivigia-ha&category=integration) |
| JackSignal | [jacksignal](custom_components/jacksignal/) | [![Instalar JackSignal desde el Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Gente-del-Condado&repository=jacksignal-ha&category=integration) |
| Headscale Gateway | [headscale_gateway](custom_components/headscale_gateway/) | [![Instalar Headscale Gateway desde el Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Gente-del-Condado&repository=headscale-gateway-ha&category=integration) |

Los proyectos publican únicamente su integración mediante GitHub Actions en Mis-component de Forgejo. Forgejo replica el catálogo a GitHub. Para instalar aplicaciones del Supervisor, usa [Mis-app](https://github.com/Gente-del-Condado/Mis-app).

## Instalar o actualizar Forgejo Backup

1. En **Repositorios**, añade este catálogo con su URL SSH, rama `main` y una clave de despliegue de lectura. Verifica la huella del servidor y sincroniza.
2. En **Componentes**, busca **Forgejo Backup**. Pulsa **Instalar integración** o **Actualizar integración**, revisa el commit y confirma.
3. Reinicia Home Assistant Core. Para el primer uso, añade **Private Git Manager · Forgejo Backup** en **Ajustes → Dispositivos y servicios**.

Forgejo Backup necesita otro repositorio privado para almacenar las copias cifradas. La integración genera su propia clave de despliegue con escritura y mantiene el índice de copias recientes en el README que crea en ese destino.

[Instalar componentes](https://gente-del-condado.github.io/HA-Private-Git-Manager/#componentes) · [Configurar Forgejo Backup y recuperar copias](https://gente-del-condado.github.io/HA-Private-Git-Manager/#copias-forgejo)

El código se mantiene en [HA-Private-Git-Manager](https://github.com/Gente-del-Condado/HA-Private-Git-Manager). El flujo de publicación sincroniza la integración desde allí.
