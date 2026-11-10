# JackSignal para Home Assistant

Avisos, música y voz por la salida de audio local de Home Assistant: sonidos de Alarmo, apertura y cierre de sensores, anuncios de temperatura y recepción DLNA de audio. Un único reproductor evita que los avisos se superpongan y aplica sus prioridades.

JackSignal utiliza **FFmpeg y la salida PulseAudio predeterminada**. Puede ser el jack de una Raspberry Pi; la salida se elige en el sistema de audio del equipo. La configuración se realiza con formularios nativos de Home Assistant, disponibles en español e inglés.

## Elegir cómo instalar

Usa **una sola vía para gestionar las actualizaciones** de la integración.

| Vía | Repositorio | Qué instala |
| --- | --- | --- |
| Tienda de aplicaciones de Home Assistant OS | [Mis-app](https://github.com/Gente-del-Condado/Mis-app) | **JackSignal Installer**, que copia la integración al iniciarlo |
| HACS / Marketplace, como repositorio personalizado de integración | [jacksignal-ha](https://github.com/Gente-del-Condado/jacksignal-ha) | La integración directamente |
| Private Git Manager | [Mis-component](https://github.com/Gente-del-Condado/Mis-component), carpeta `custom_components/jacksignal` | La integración directamente |
| Manual | [jacksignal-ha](https://github.com/Gente-del-Condado/jacksignal-ha) | Copia de `custom_components/jacksignal` a `/config/custom_components/jacksignal` |

El repositorio `Mis-component` agrupa varias integraciones; para HACS utiliza **jacksignal-ha**. Añadir un repositorio personalizado no significa que JackSignal esté incluido en el catálogo predeterminado de HACS.

### Con JackSignal Installer

1. Añade `https://github.com/Gente-del-Condado/Mis-app` en los repositorios de la tienda de aplicaciones. En versiones anteriores se llama tienda de complementos.
2. Instala **JackSignal Installer**, pulsa **Iniciar** y comprueba el registro.
3. El instalador termina y se detiene: es su funcionamiento normal. Reinicia Home Assistant.
4. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → JackSignal**.

Para actualizar: actualiza la aplicación, vuelve a pulsar **Iniciar**, comprueba el registro y reinicia Home Assistant. No actives el inicio automático: el instalador usa `manual_only`. Conserva los sonidos y la configuración; al reemplazar el código guarda la versión anterior en `/config/.jacksignal-previous`.

### Con HACS / Marketplace o instalación manual

Añade `https://github.com/Gente-del-Condado/jacksignal-ha` como repositorio personalizado de categoría **Integración** e instálalo. Reinicia Home Assistant y añade JackSignal desde **Dispositivos y servicios**. Tras actualizar el código, vuelve a reiniciar Home Assistant.

[Instalar desde Marketplace](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Gente-del-Condado&repository=jacksignal-ha&category=integration).

Se toma **Home Assistant 2026.11.0** como versión mínima de esta distribución. En Home Assistant Container, instala la integración directamente y proporciona FFmpeg, FFprobe y acceso a PulseAudio en el contenedor. Instalar el código por sí solo no proporciona la salida de audio.

## Primera prueba y biblioteca de sonidos

1. Sube tus archivos desde **Multimedia → Mis archivos multimedia** de Home Assistant.
2. Abre **JackSignal → Configurar** y utiliza la prueba de sonido, o selecciona JackSignal como reproductor en Multimedia.
3. Comprueba que la salida PulseAudio predeterminada es la deseada. En Home Assistant OS puedes consultar `ha audio info`.

Admite MP3, WAV, Ogg, Opus, FLAC, M4A y AAC, además de URLs HTTP(S) de audio accesibles desde Home Assistant. La subida y eliminación de archivos se gestiona desde Multimedia. No necesitas un script por sonido.

El reproductor suele llamarse `media_player.jacksignal`; comprueba el identificador de tu instalación. Ofrece reproducir, pausar, detener, volumen y silencio. **Volumen y silencio afectan a toda la salida PulseAudio predeterminada**, incluidas otras aplicaciones que la utilicen.

## Alarmo y sensores de apertura/cierre

En **JackSignal → Configurar**:

1. Vincula tu panel de Alarmo.
2. Asigna sonidos a sus eventos: armado, desarmado, cuenta atrás de entrada/salida, fallo al armar y alarma disparada. Para una sirena, elige alarma disparada, prioridad crítica y repetición.
3. En los campos **APERTURA** selecciona estado, sonido y condición; haz lo mismo en **CIERRE**. Cada aviso necesita su archivo, aunque puedes elegir el mismo para ambos. «Siempre» no asigna un sonido. Cada transición permite **nunca**, **solo desarmada** o **siempre**; si activas un aviso sin sonido, el formulario te pedirá seleccionarlo.
4. Consulta **Ver sonidos asignados** para revisar eventos, sensores, frases de voz, prioridades y asignaciones vacías. El resumen incluye sensores de apertura disponibles y reglas guardadas; no representa una lista exacta de los sensores de Alarmo.

Puedes activar por separado el aviso cuando un sensor impide armar Alarmo. Asignar ese aviso no activa automáticamente el sonido al abrir: debes elegir su condición. Si varios sensores impiden armar, se selecciona el aviso de mayor prioridad; un empate conserva el primero del evento.

Los sensores binarios con condición **siempre** funcionan sin Alarmo. **Solo desarmada** requiere un panel vinculado, disponible y desarmado. Los avisos se disparan por cambios reales `off → on` o `on → off` de forma predeterminada; no al arrancar ni al recuperar un sensor desconectado. Desde 0.7.3, el formulario propone automáticamente un par de estados al añadir el sensor y permite editar apertura y cierre por separado, incluidos valores personalizados. Para sensores habituales de Home Assistant propone `on`/`off`, aunque visualmente se muestren como «abierto/cerrado». Reconoce también formatos como `true`/`false`, `open`/`closed` y `1`/`0`, pero debes comprobar su significado físico: algunos contactos Zigbee usan `true` para cerrado. La propuesta depende del estado interno disponible; si está desconectado se usa `on`/`off` como punto de partida. Las reglas guardadas conservan tus valores y las antiguas mantienen su interpretación previa. Apertura y cierre deben ser distintos; `unknown` y `unavailable` no son estados configurables. Para eliminar una regla, selecciona «Nunca» en ambos avisos y borra los dos sonidos.

Desactiva las acciones antiguas que ejecuten FFmpeg directamente cuando hayas comprobado las reglas nuevas: el audio externo a JackSignal no participa en sus prioridades.

## Texto a voz sin YAML

En **Configurar → Configurar voz de un sensor**:

1. Selecciona un sensor y un motor TTS previamente configurado en Home Assistant.
2. Escribe el texto anterior y posterior al valor. Por ejemplo: **La temperatura del salón es** + valor + **grados Celsius**. Desactiva la unidad automática si ya la has escrito.
3. Elige prioridad y disparador: manual, cambio de valor, superar un umbral o bajar de un umbral.
4. Usa **Probar sin guardar** y después **Guardar**. Vuelve a elegir el sensor para editar o eliminar su regla.

Se guarda una regla por sensor. El motor usa su voz e idioma predeterminados. Los textos son literales, sin plantillas YAML/Jinja. Los sensores binarios leen `on`/`off`; para avisos distintos al abrir y cerrar utiliza las reglas de sonido.

Los umbrales actúan al cruzarlos. El intervalo mínimo entre avisos automáticos es de 60 segundos por defecto: descarta avisos próximos, no los pone en espera. No anuncia valores desconocidos/no disponibles ni cambios de recuperación al arrancar.

Desde el editor visual de automatizaciones puedes ejecutar **JackSignal · Decir valor del sensor**. Usa la frase, motor y prioridad guardados; la llamada manual no está limitada por el disparador ni por el intervalo automático. También puedes enviar `tts.speak` al reproductor, con prioridad baja. La URL del audio generado por TTS debe ser accesible desde Home Assistant.

## Cualquier evento o automatización

Añade la acción visual **JackSignal · Reproducir aviso**, selecciona el sonido y su prioridad. Puedes usar cualquier disparador de Home Assistant: botón, horario, sensor o evento. No necesita Alarmo ni un script por archivo.

Ejemplo opcional en YAML:

```yaml
action: jacksignal.play_sound
data:
  sound:
    media_content_id: media-source://media_source/local/aviso.mp3
    media_content_type: music
  priority: low
```

`media_player.play_media` y el TTS enviado directamente al reproductor usan prioridad baja. Para elegir otra prioridad utiliza las acciones de JackSignal o sus reglas configuradas.

## Prioridades: qué ocurre si llega otro sonido

| Prioridad | Valor | Uso orientativo |
| --- | --- | --- |
| Baja | 0 | Música, DLNA y voz informativa |
| Normal | 1 | Avisos habituales |
| Alta | 2 | Avisos importantes |
| Crítica | 3 | Sirena de alarma |

Un aviso de prioridad **igual o superior** detiene y reemplaza el audio actual. Uno de menor prioridad se descarta: no hay cola ni mezcla. La música interrumpida no se reanuda automáticamente. Al terminar un archivo se añade un segundo de silencio para que PulseAudio no recorte su final; el reproductor puede seguir activo brevemente durante ese margen.

La **sirena crítica repetitiva de Alarmo** está protegida frente a otros avisos hasta que el panel salga del estado disparado. Los controles manuales de Home Assistant siguen disponibles. DLNA no puede detener ni modificar un aviso de prioridad superior. Puedes consultar `priority` y `alarm_event` en los atributos del reproductor.

## DLNA/UPnP: enviar audio por la red

El receptor es opcional y solo admite audio. Actívalo en **Configurar → DLNA: red y puerto**. Una aplicación emisora compatible con **UPnP MediaRenderer** verá **JackSignal Audio**.

- Selecciona una IPv4 del equipo visible desde Home Assistant. Se escucha en una sola dirección; puede corresponder a Ethernet, Wi-Fi o una VPN.
- El puerto HTTP predeterminado es **49200** y se puede cambiar. El descubrimiento SSDP utiliza UDP **1900**.
- Para redes enrutadas sin multicast, desactiva SSDP y añade `http://IP:PUERTO/description.xml` en un emisor que admita receptores manuales. No es una página para subir archivos.
- Con Tailscale/WireGuard en otro contenedor, su IP no pertenece necesariamente a Home Assistant: puede hacer falta una ruta hacia la IP local. Deben funcionar el control, las notificaciones de vuelta y el acceso a la URL del audio.

El emisor debe servir el archivo mediante una URL HTTP(S) accesible desde la Raspberry. El receptor comprueba el contenido y rechaza vídeos, aunque tengan extensión de audio; admite carátulas adjuntas. No ofrece búsqueda de posición ni listas de reproducción.

**No es un receptor Google Cast, AirPlay ni Spotify Connect.** El botón Chromecast de VLC utiliza otro protocolo. DLNA no lleva autenticación: úsalo en redes de confianza y no lo publiques directamente en Internet.

## Si algo no funciona

| Síntoma | Comprobación |
| --- | --- |
| El instalador aparece detenido | Es normal tras copiar la integración. Revisa su registro y reinicia Home Assistant. |
| Error al cambiar el arranque (`manual_only`) | Déjalo en arranque manual y pulsa Iniciar únicamente para instalar/actualizar. |
| La versión de la integración no cambia | Actualizar la aplicación no ejecuta el instalador: pulsa Iniciar y reinicia Home Assistant. |
| La prueba suena, pero abrir una ventana no | Revisa la condición de apertura, el panel si usas «solo desarmada» y la prioridad actual. El fallo al armar es una opción independiente. |
| No aparece un motor de voz | Configura primero una integración TTS en Home Assistant. |
| No suena ningún medio | Comprueba FFmpeg, PulseAudio y su salida predeterminada; una ruta del host no siempre existe dentro de Home Assistant. |
| No aparece el receptor DLNA | Revisa la interfaz elegida, SSDP, cortafuegos y compatibilidad del emisor; Cast no es DLNA. |

Si un sensor no avisa, comprueba por separado su sonido y condición de apertura y cierre. En el formulario puedes consultar el estado interno y seleccionar el que realmente significa abierto. Cambiar esta selección no cambia el sensor ni su configuración en Alarmo. Puedes activar el registro de depuración de la integración desde Dispositivos y servicios, reproducir el problema y desactivarlo para descargar el registro: muestra si el aviso fue descartado por condición, falta de sonido o prioridad, o si otro audio lo interrumpió.

Para informar de un problema, indica versiones de Home Assistant y JackSignal, método de instalación, pasos y registros relevantes, sin credenciales: [incidencias](https://github.com/Gente-del-Condado/jacksignal-ha/issues).

## Estado y desarrollo

La instalación y la reproducción local han sido probadas en una Raspberry Pi 4B. Las pruebas automáticas cubren prioridades, reglas, voz, formularios, instalación y DLNA. La voz con cada motor real, la pausa/reanudación física y la compatibilidad de emisores/redes DLNA requieren validación en el equipo correspondiente.

[Proyecto de origen](https://github.com/Gente-del-Condado/jacksignal) · [Código principal en Forgejo](https://gentedelcondado.es/forgejo/wolfbelmi88/jacksignal) · [Historial de versiones de la aplicación](https://github.com/Gente-del-Condado/Mis-app/blob/main/jacksignal_installer/CHANGELOG.md).

## English

JackSignal provides a Home Assistant media player using FFmpeg and the default PulseAudio output. It supports Alarmo alerts, independent binary-sensor opening/closing sounds, sensor speech configured without YAML, and an optional audio-only DLNA renderer. Configure a TTS engine separately before using speech.

Install the integration from the custom **jacksignal-ha** repository, or use **JackSignal Installer** from **Mis-app** on Home Assistant OS. With the installer, click **Start**, check its log, then restart Home Assistant. Repeat those steps after updating the installer. It intentionally stops after copying the integration and does not support automatic startup. Use one installation method to manage updates.

Upload clips in Home Assistant Media. Under JackSignal's configuration, assign sounds and speech rules and review assignments. Use the visual **Play alert** or **Speak sensor value** actions in any automation. Higher or equal priorities replace current audio; lower priorities are dropped. A repeating critical alarm siren is protected. Interrupted music is not resumed. DLNA is not Cast, AirPlay or Spotify Connect.
