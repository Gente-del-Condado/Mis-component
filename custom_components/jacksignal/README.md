# JackSignal para Home Assistant

Avisos, música y voz por la salida de audio local de Home Assistant: sonidos de Alarmo, apertura y cierre de sensores, anuncios de temperatura y recepción DLNA de audio. Un único reproductor evita que los avisos se superpongan y aplica sus prioridades.

JackSignal utiliza **FFmpeg y la salida PulseAudio predeterminada**. Puede ser el jack de una Raspberry Pi; la salida se elige en el sistema de audio del equipo. La configuración se realiza con formularios nativos de Home Assistant, disponibles en español e inglés.

## Elegir cómo instalar

Usa **una sola vía para gestionar las actualizaciones** de la integración.

| Vía | Repositorio | Qué instala |
| --- | --- | --- |
| Tienda de aplicaciones de Home Assistant OS | [Mis-app](https://github.com/Gente-del-Condado/Mis-app) | **Instalador de JackSignal**, que copia la integración al iniciarlo |
| HACS / Marketplace, como repositorio personalizado de integración | [jacksignal-ha](https://github.com/Gente-del-Condado/jacksignal-ha) | La integración directamente |
| Manual | [jacksignal-ha](https://github.com/Gente-del-Condado/jacksignal-ha) | Copia de `custom_components/jacksignal` a `/config/custom_components/jacksignal` |

Para instalar desde HACS / Marketplace utiliza **jacksignal-ha**. Añadir este repositorio personalizado no significa que JackSignal esté incluido en el catálogo predeterminado.

### Con Instalador de JackSignal

1. Añade `https://github.com/Gente-del-Condado/Mis-app` en los repositorios de la tienda de aplicaciones. En versiones anteriores se llama tienda de complementos.
2. Instala **Instalador de JackSignal**, pulsa **Iniciar** y comprueba el registro.
3. El instalador termina y se detiene: es su funcionamiento normal. Reinicia Home Assistant.
4. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → JackSignal**.

Para actualizar: actualiza la aplicación, vuelve a pulsar **Iniciar**, comprueba el registro y reinicia Home Assistant. No actives el inicio automático: el instalador usa `manual_only`. Conserva los sonidos y la configuración; al reemplazar el código guarda la versión anterior en `/config/.jacksignal-previous`.

### Con Marketplace (Home Assistant 2026.11 o posterior)

Añade `https://github.com/Gente-del-Condado/jacksignal-ha` como repositorio personalizado de categoría **Integración** e instálalo. En una primera instalación, si JackSignal no se había cargado antes, Marketplace puede abrir su configuración inmediatamente: JackSignal dispone de configuración gráfica y no necesita un reinicio previo en ese caso.

Si ya estaba cargado o estás actualizando, sigue el aviso de reinicio que muestre Home Assistant. No confundas esta instalación con **Instalador de JackSignal**, que copia archivos y sigue requiriendo iniciar el instalador y reiniciar Home Assistant. Si eliges la instalación manual, reinicia después de copiar el código.

Marketplace ya no administra AppDaemon ni Python Scripts. JackSignal es una **integración**, no uno de esos tipos, por lo que ese cambio no le afecta. [Funcionamiento oficial de Marketplace](https://contributors.home-assistant.io/marketplace/how-it-works/).

[Instalar desde Marketplace](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Gente-del-Condado&repository=jacksignal-ha&category=integration).

Se toma **Home Assistant 2026.11.0** como versión mínima de esta distribución. En Home Assistant Container, instala la integración directamente y proporciona FFmpeg, FFprobe y acceso a PulseAudio en el contenedor. Instalar el código por sí solo no proporciona la salida de audio.

## Primera prueba y biblioteca de sonidos

1. Sube tus archivos desde **Multimedia → Mis archivos multimedia** de Home Assistant.
2. Abre **JackSignal → Configurar** y utiliza la prueba de sonido, o selecciona JackSignal como reproductor en Multimedia.
3. Comprueba que la salida PulseAudio predeterminada es la deseada. En Home Assistant OS puedes consultar `ha audio info`.

Admite MP3, WAV, Ogg, Opus, FLAC, M4A y AAC, además de URLs HTTP(S) de audio accesibles desde Home Assistant. La subida y eliminación de archivos se gestiona desde Multimedia. No necesitas un script por sonido.

El reproductor suele llamarse `media_player.jacksignal`; comprueba el identificador de tu instalación. Ofrece reproducir, pausar, detener, volumen y silencio. **Volumen y silencio afectan a toda la salida PulseAudio predeterminada**, incluidas otras aplicaciones que la utilicen.

## Gestionar avisos desde el panel

Desde la versión **0.10.0**, abre **JackSignal** en la barra lateral de Home Assistant o **JackSignal → Configurar → Gestionar avisos**. El panel y sus acciones requieren una cuenta administradora. La interfaz está en español y se adapta a móvil y escritorio.

- **Sensores, Alarmo y Voz:** cada sección muestra los avisos correspondientes. Los sensores disponibles y las reglas guardadas aparecen incluso cuando todavía no tienen sonido o el sensor ya no está disponible.
- **Buscar:** filtra por nombre, identificador de sensor, archivo de sonido o texto de voz; ignora diferencias de mayúsculas y tildes.
- **Mostrar:** todos, configurados y activados, sin configurar o desactivados. Se muestran hasta 60 resultados inicialmente; **Mostrar más** amplía la lista.
- **Editar / Configurar:** modifica el aviso directamente. Apertura y cierre tienen bloques separados y cada condición activa requiere su propio sonido. Los estados técnicos del sensor quedan en **Opciones avanzadas**. Los cambios solo se aplican al guardar.
- **Activar / Desactivar:** conserva archivos, condiciones, prioridad y texto de voz. Las reglas existentes siguen activadas por defecto. Un aviso de voz desactivado tampoco se ejecuta desde su acción de automatización. Desactivar la regla de sirena disparada detiene su sirena; reactivarla con el panel todavía disparado puede restaurar la repetición configurada. Para otros avisos, desactivar evita nuevos disparos, sin cancelar un clip que ya haya comenzado.
- **Probar apertura / Probar cierre / Probar / Escuchar:** usa la configuración guardada, siempre con prioridad baja **P0**, sin repetición. No cambia el estado de Alarmo ni de los sensores y no activa una regla desactivada. Un aviso de prioridad superior o una sirena protegida bloquean la prueba. **Detener prueba** solo detiene el audio iniciado desde este panel.
- **Vista compacta y resumen:** contadores globales de activados, desactivados y sin configurar. El estado de reproducción se consulta cada cinco segundos mientras la página está visible. Los estados de sensores se renuevan con Actualizar.
- **Selección múltiple:** marca hasta 200 avisos configurados de la sección actual y cambia activación o prioridad. Revisa la lista antes de guardar: los cambios se validan y aplican juntos. Cambiar sección, búsqueda o filtro limpia la selección.
- **Copiar a…:** reutiliza un aviso de sensor o voz en otro sensor de la misma sección. Revisa la copia antes de guardar; reemplaza el aviso del destino, comienza desactivada y conserva la polaridad del sensor de destino.
- **Actualizar:** vuelve a leer las reglas y los estados actuales. Si otra pantalla ha cambiado la configuración, se rechaza el guardado obsoleto para evitar sobrescribirla: cierra el editor, actualiza y vuelve a editar.

Los sonidos se seleccionan de los directorios de **Mis medios**; para subir un archivo usa **Configuración y audio → Enviar audio** o Multimedia. La lista del editor está limitada a 2000 archivos y 2000 carpetas; si se alcanza el límite, se muestra un aviso y se conservan las selecciones anteriores. El formulario tradicional sigue disponible para bibliotecas mayores. El resumen de asignaciones en texto también se conserva como alternativa.

## Alarmo y sensores de apertura/cierre

En **JackSignal → Configurar**:

1. Vincula tu panel de Alarmo.
2. Asigna sonidos a sus eventos: armado, desarmado, cuenta atrás de entrada/salida, fallo al armar y alarma disparada. Para una sirena, elige alarma disparada, prioridad crítica y repetición.
3. En los campos **APERTURA** selecciona estado, sonido y condición; haz lo mismo en **CIERRE**. Cada aviso necesita su archivo, aunque puedes elegir el mismo para ambos. «Siempre» no asigna un sonido. Cada transición permite **nunca**, **solo desarmada** o **siempre**; si activas un aviso sin sonido, el formulario te pedirá seleccionarlo.
4. Consulta **Ver sonidos asignados** para revisar eventos, sensores, frases de voz, prioridades y asignaciones vacías. El resumen incluye sensores de apertura disponibles y reglas guardadas; no representa una lista exacta de los sensores de Alarmo.

Puedes activar por separado el aviso cuando un sensor impide armar Alarmo. Asignar ese aviso no activa automáticamente el sonido al abrir: debes elegir su condición. Si varios sensores impiden armar, se selecciona el aviso de mayor prioridad; un empate conserva el primero del evento.

Los sensores binarios con condición **siempre** funcionan sin Alarmo. **Solo desarmada** requiere un panel vinculado, disponible y desarmado. Los avisos se disparan por cambios reales `off → on` o `on → off` de forma predeterminada; no al arrancar ni al recuperar un sensor desconectado. Desde 0.7.3, el formulario propone automáticamente un par de estados al añadir el sensor y permite editar apertura y cierre por separado, incluidos valores personalizados. Para sensores habituales de Home Assistant propone `on`/`off`, aunque visualmente se muestren como «abierto/cerrado». Reconoce también formatos como `true`/`false`, `open`/`closed` y `1`/`0`, pero debes comprobar su significado físico: algunos contactos Zigbee usan `true` para cerrado. La propuesta depende del estado interno disponible; si está desconectado se usa `on`/`off` como punto de partida. Las reglas guardadas conservan tus valores y las antiguas mantienen su interpretación previa. Apertura y cierre deben ser distintos; `unknown` y `unavailable` no son estados configurables. Para eliminar una regla, selecciona «Nunca» en ambos avisos y borra los dos sonidos.

Desactiva las acciones antiguas que ejecuten FFmpeg directamente cuando hayas comprobado las reglas nuevas: el audio externo a JackSignal no participa en sus prioridades.

## Voz general e instalación asistida (0.13.0)

En **JackSignal → Voz → Configurar voz general**, elige el motor predeterminado, idioma, voz y velocidad. Si hay un único motor Piper de Wyoming conectado, se propone automáticamente, aunque hayas cambiado su nombre. El idioma automático prefiere español y la velocidad inicial es 1×. Si hay varios Piper, selecciona el adecuado; JackSignal no cambia a un motor en la nube si Piper falta.

Los avisos nuevos creados desde el panel heredan estos valores. Para aplicar la configuración a los que ya tienes, marca **Aplicar estos valores a todos los avisos de voz existentes** y guarda. Sus textos, condiciones, activación y prioridades se conservan. En cualquier aviso puedes desmarcar **Usar motor, idioma, voz y velocidad generales** para personalizarlo. Las tarjetas indican si usan la configuración general o una propia. Los cambios generales afectan a las próximas reproducciones; no cambian un audio que ya esté sonando.

**Preparar Piper**, disponible con Supervisor, solicita confirmación en el panel antes de realizar cambios. Si falta la aplicación oficial, la instala, configura `es_ES-davefx-medium`, activa su inicio automático y la inicia. Necesita Internet, espacio libre y puede tardar varios minutos; mantén la pantalla abierta. Si ya está instalada, conserva sus opciones y solo la inicia si no está iniciada. No abre puertos ni cambia protecciones.

Después completa el descubrimiento **Wyoming** en **Dispositivos y servicios**, vuelve al panel y pulsa **Actualizar**. La aplicación instalada y la entidad TTS conectada son pasos distintos. Si la preparación falla o se pierde la conexión, consulta **Abrir Piper** y sus registros antes de reintentar: puede haber terminado solo una parte. En Home Assistant Container se puede conectar un Piper externo con Wyoming, pero no instalar una aplicación de Supervisor desde este panel.

La instalación asistida se ha verificado con respuestas simuladas de Supervisor; queda pendiente probarla en un Home Assistant OS real. Las pruebas de audio mantienen P0 y los avisos usan su prioridad habitual.

## Voz local y español

Solo aparecen motores TTS configurados en Home Assistant; JackSignal no instala motores por su cuenta. Para una Raspberry Pi 4 recomendamos **Piper** con una voz española de calidad `medium` o inferior:

1. En **Ajustes → Aplicaciones → Instalar aplicación**, instala **Piper**.
2. Selecciona una voz española en su configuración e inicia la aplicación. Si tu versión ofrece varios motores, usa el backend `piper`.
3. En **Ajustes → Dispositivos y servicios**, añade la integración **Wyoming** descubierta para Piper.
4. Abre el panel **JackSignal**, pulsa **Actualizar**, entra en **Voz** y edita el aviso. Selecciona Piper, el idioma español que anuncie y su voz; escucha la prueba y guarda.

Piper genera voz localmente una vez descargado el modelo. También puedes ejecutarlo en otro ordenador de tu red y conectarlo mediante Wyoming. No necesitas micrófono ni un motor de reconocimiento de voz para leer sensores.

Si Google Translate habla en inglés, selecciona **es** en el idioma del aviso. El idioma de la interfaz de Home Assistant no fija el idioma de síntesis. Google Translate necesita Internet; Piper permite mantener la síntesis en casa. El panel muestra los idiomas y voces que cada motor anuncia, no una lista fija. Si no aparecen voces españolas en Piper, configura/instala una en la aplicación y recarga Wyoming. La opción **Automático** prefiere español de España, después español genérico y después otra variante española disponible. Si no existe ninguna, utiliza el idioma predeterminado del motor. La voz automática se elige dentro del idioma efectivo. Puedes cambiar idioma y voz por aviso; las selecciones explícitas se respetan.

Consulta la [documentación oficial de Piper](https://github.com/home-assistant/apps/blob/master/piper/DOCS.md) y [Google Translate TTS](https://www.home-assistant.io/integrations/google_translate/).

## Velocidad por aviso (0.12.0)

En **JackSignal → Voz → Editar**, ajusta **Velocidad de voz**, pulsa **Escuchar antes de guardar (P0)** y guarda. El rango es de **0,5× a 2×**: `0,8` más lento, `1` normal, `1,2` más rápido. La tarjeta muestra el valor guardado. Las reglas anteriores usan `1×`; copiar o desactivar un aviso conserva su velocidad.

JackSignal ajusta el tempo del audio generado conservando el tono, tanto con Piper como con otros motores. Este multiplicador se aplica sobre la velocidad configurada en el motor: si cambiaste `length_scale` en Piper, ambos ajustes se combinan. Para una referencia normal común puedes dejar `length_scale` en `1.0` y ajustar cada aviso en JackSignal. No necesitas reiniciar Piper al cambiar la velocidad de un aviso.

Las pruebas siguen usando P0 y las reproducciones automáticas usan la prioridad guardada. El ajuste no afecta a música, DLNA ni sonidos de Alarmo. El formulario nativo de voz conserva la velocidad elegida en el panel.

## Texto a voz sin YAML

En **Configurar → Configurar voz de un sensor**:

1. Selecciona un sensor y un motor TTS previamente configurado en Home Assistant.
2. Escribe el texto anterior y posterior al valor. Por ejemplo: **La temperatura del salón es** + valor + **grados Celsius**. Desactiva la unidad automática si ya la has escrito.
3. Elige prioridad y disparador: manual, cambio de valor, superar un umbral o bajar de un umbral.
4. Usa **Probar sin guardar** y después **Guardar**. Vuelve a elegir el sensor para editar o eliminar su regla.

Se guarda una regla por sensor. En **JackSignal → Voz → Editar**, elige el motor, el idioma y una voz compatible; puedes ver la frase con el valor actual y **Escuchar antes de guardar (P0)**. Desde 0.12.1, las reglas sin idioma ni voz explícitos también prefieren español automáticamente. El formulario nativo conserva la selección del panel mientras no cambies de motor. Los textos son literales, sin plantillas YAML/Jinja. En **JackSignal → Voz → Editar → Qué dice cada estado**, añade equivalencias como `on → abierta` y `off → cerrada`. Con el texto previo «La ventana está», la voz dirá «La ventana está abierta». Puedes elegir «encendido/apagado» u otras palabras para cada estado exacto (`true`, `false`, `open`, `closed`, etc.). Sin equivalencia se lee el valor original; los disparadores y umbrales siguen usando el estado real. La vista previa y las tarjetas muestran la configuración, y el formulario nativo la conserva. Las prioridades de Alarmo no cambian.

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

## Enviar audio y consultar el diagnóstico

En **JackSignal → Configurar → Enviar audio** puedes subir un archivo desde el móvil/PC, pegar una URL HTTP(S) directa de audio o elegir un archivo de Mis medios. No necesitas activar DLNA para estos envíos: utilizan tu acceso autenticado a Home Assistant y también sirven a través de una VPN que permita acceder a Home Assistant. Una URL debe ser accesible desde Home Assistant, no solo desde el móvil.

Los archivos se comprueban con FFprobe: se rechazan vídeos, archivos vacíos y contenido no reconocido como audio; se permiten portadas de álbum. Las subidas admiten hasta 100 MB y los audios válidos quedan en **Mis medios → jacksignal** con un nombre único, sin sobrescribir otros sonidos. Puedes reutilizarlos o borrarlos desde Mis medios. Se conservan incluso si una alarma impide reproducirlos. Las URLs no se guardan en la configuración. Una página de Spotify o YouTube no es una URL directa de audio.

Todo envío directo tiene prioridad **P0 (baja)** y pasa por el mismo reproductor. Alarmo y los avisos de mayor prioridad pueden interrumpirlo; la música no se reanuda después. **Detener solo el envío directo** no detiene Alarmo ni otros propietarios de reproducción. El indicador ✓ confirma que se aceptó la reproducción, no que haya sonado físicamente.

En **Configurar → Diagnóstico DLNA** verás el estado real del receptor, SSDP habilitado, URL de descripción, actividad/prioridad del reproductor, última petición HTTP (UTC, IP, método y resultado) y último error HTTP o de arranque observado. El botón **Diagnóstico DLNA** actualiza la vista. Los datos se reinician al recargar la integración y no incluyen URLs de audio ni credenciales. SSDP habilitado no garantiza que un móvil reciba multicast; una petición HTTP puede proceder de un navegador, no necesariamente de un controlador. BubbleUPnP ya ha sido probado por el usuario con audio en Raspberry Pi 4B por Ethernet y Android por Wi-Fi.

### Nombre del receptor y varias estancias

Desde la versión 0.9.0, **Configurar → DLNA: red y puerto → Nombre del receptor en la red** permite elegir un nombre de 1 a 64 caracteres, como **JackSignal · Salón** o **JackSignal · Cocina**. Se admiten tildes y se conserva el identificador del receptor. Las instalaciones anteriores mantienen **JackSignal Audio** hasta que lo cambies. Guardar reinicia el receptor y puede detener la música recibida por DLNA; actualiza después la lista de dispositivos de BubbleUPnP. El nuevo nombre también aparece en el diagnóstico y en `friendlyName` de `description.xml`.

El nombre DLNA es independiente del nombre de la entidad en Home Assistant. Para identificar el mismo equipo en ambos sitios puedes poner nombres equivalentes. Cada instalación de Home Assistant tiene un único reproductor local JackSignal; varias Raspberry con instalaciones independientes pueden anunciar nombres distintos en la misma red y utilizar el mismo puerto en sus respectivas IP. Gestionar varias salidas remotas desde una sola instalación no está implementado.

### Prueba del diagnóstico, envío y prioridades

1. En **Configurar → Diagnóstico DLNA**, comprueba el receptor HTTP, SSDP y la dirección anunciada. Abre esa dirección desde el móvil y vuelve a pulsar **Diagnóstico DLNA**: aparecerá una petición HTTP reciente. Esto comprueba HTTP; localizar el receptor en BubbleUPnP comprueba además el descubrimiento desde ese móvil.
2. En **Enviar audio → Subir archivo de audio**, selecciona un MP3 o WAV de 20 segundos. Se valida, se guarda en **Mis medios → jacksignal** y se reproduce con P0. El indicador ✓ confirma la aceptación; comprueba también que se escuche completo.
3. En **Enviar audio → Reproducir URL de audio**, pega un enlace HTTP(S) directo a un MP3 o una radio accesible desde Home Assistant. Una página web o el enlace del XML DLNA no son audio. Para una prueba local, si ya tienes un audio en `/config/www/prueba.mp3`, su URL habitual es `http://IP_DE_HOME_ASSISTANT:8123/local/prueba.mp3`; adapta protocolo, dirección y puerto a tu instalación. Los archivos de `www` se sirven sin autenticación: utiliza únicamente un audio de prueba que puedas compartir.
4. Comprueba en **Ver sonidos asignados** que el aviso de Alarmo usado en la prueba tenga prioridad P2 o P3 y un archivo suficientemente largo. Por ejemplo, puedes usar el evento **Alarma desarmada** durante un ciclo normal y controlado de armado/desarmado; no necesitas disparar una intrusión real.
5. Mientras suena música P0, provoca ese evento: el aviso debe sustituir la música. Mientras dure el aviso, intenta enviar otro archivo o URL: debe rechazarse por prioridad. **Detener solo el envío directo** tampoco debe cortar el aviso. Al terminar, envía de nuevo la música: debe reproducirse. La música interrumpida no se reanuda automáticamente.

La prioridad depende de la regla configurada: un aviso de Alarmo configurado en P0 no tiene preferencia sobre otro audio P0. Una sirena crítica repetitiva activa tiene protección adicional. No cambies temporalmente una regla de seguridad sin restaurarla al terminar la prueba.

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
