// The front page (index.html): its words in the visitor's language (or the
// one picked with ?lang=), the device it is opened on, and that device's
// file from latest.json (written at each release beside this page; GitHub's
// API only when it is missing).
(function () {
  var WORDS = {
    en: {
      pageTitle: 'Dannify: music for every device',
      navFeatures: 'Features', navDownload: 'Download', navAndroid: 'Android', navFaq: 'Questions',
      title: 'Search anything.<br><em>Play it now.</em><br>Keep it.',
      lead: 'A music player for your computer, phone and TV. Free, with no ads, and it keeps itself up to date.',
      getAll: 'Download Dannify', getFor: 'Download for {p}', version: 'Version {v} · {size}',
      otherMac: 'Mac with an Intel processor? <a href="{url}">Get that one</a>.',
      otherPlatforms: 'Another device? <a href="#download">All downloads</a>',
      howTitle: 'How to install',
      runsOn: 'Dannify runs on', tWin: '10 and 11', tMac: 'Apple silicon and Intel', notYet: 'Not yet',
      andEyebrow: 'Phones, tablets and TVs', andTitle: 'Dannify for Android',
      andSub: 'The same Dannify on your phone, your tablet and your TV. Free, with no ads, and it keeps itself up to date there too.',
      and7: 'Android 7.0 and later',
      andPerks: ['A widget for your home screen', 'Plays on the lock screen and in the notification', 'Your headphones’ buttons play along', 'At home on a tablet too'],
      andScan: 'On a computer? Scan this with your phone’s camera to get Dannify there.',
      tvRemote: 'Moved around with the remote',
      tv64: 'Dannify needs a 64-bit TV or stick. Many older sticks are 32-bit and cannot run it yet.',
      featuresTitle: 'Everything music, in one app', featuresSub: 'The same Dannify on your computer, your phone and your TV.',
      f1: 'Play anything, at once', f1t: 'Search the whole catalogue and play in a moment. Charts and new music where you are, moods and genres.',
      f1x: 'A song starts in about a third of a second, and what is already in your library comes first.',
      f2: 'Keep what you love', f2t: 'Saved songs come with their artwork, tags and lyrics, and play without a connection.',
      f2x: 'At ease offline, and Dannify picks up where you left off, down to the second.',
      f3: 'Lyrics in time', f3t: 'Words light up as they are sung. Missing or off? Fix them, and everyone gets the fix.',
      f3x: 'Running early or late? Click the line you hear and the words line up. A song with none? Write them and tap the timing in.',
      f4: 'Listen together', f4t: 'Start a room, share its code, and everyone hears the same song at the same moment. Chat and reactions included.',
      f4x: 'Guests can suggest songs too, each on their own device. Free, with no account needed.',
      f5: 'Your music, told back', f5t: 'History, your stats, mixes that keep up with you, and your year in music as a story.',
      f5x: 'Today, this week, this month and this year at a glance, with your streaks and the artists you played most.',
      f6: 'Paste a link', f6t: 'A Spotify song, album, playlist or artist opens ready to play and save.',
      f7: 'Special days, wherever you are',
      f7t: 'The New Year, Ramadan and Eid, Diwali, Christmas and many more, on your country’s own dates. Each one comes with its own look and its own music.',
      moreTitle: 'And more',
      fDesk: 'At home on your computer', fDeskT: 'A real window, a tray icon, and your keyboard’s media keys.',
      fLang: 'Six languages',
      fUpd: 'Up to date by itself', fUpdT: 'Install once. Each update is checked against Dannify’s signature before it goes in.',
      fLight: 'Dark or light', fLightT: 'A dark look and a light one. Pick the one you like.',
      fFree: 'Free, with no ads', fFreeT: 'No ads, and no account needed to search and play.',
      dlTitle: 'Download', dlSub: 'One file for each device. Dannify keeps itself up to date after that.',
      note: 'Every file is signed by Dannify, and the app checks each update’s signature before taking it. Not on this list: iPhone and iPad.',
      faqTitle: 'Questions',
      q1: 'Is Dannify free?', a1: 'Yes. Free to download and use, with no ads.',
      q2: 'Does it update itself?', a2: 'Yes. You install Dannify once; after that, every copy keeps itself up to date.',
      q3: 'Is it safe?', a3: 'Every file is signed by Dannify, and the app checks the signature of each update before installing it.',
      q4: 'Windows says it protected my PC', a4: 'Choose More info, then Run anyway. Windows asks only the first time.',
      q5: 'My Mac says Dannify cannot be opened',
      a5: 'Right-click Dannify in Applications, choose Open, then Open again. On macOS 15 and later: open Dannify and click Done, then in System Settings, Privacy & Security, click Open Anyway.',
      q6: 'My phone says Play Protect does not know the app', a6: 'Tap More details, then Install anyway.',
      q7: 'Will it run on my TV stick?', a7: 'If it is 64-bit, yes. Many older sticks are 32-bit and cannot run Dannify yet.',
      q8: 'Is there Dannify for iPhone or iPad?', a8: 'Not yet, sorry. For now, you can enjoy Dannify on your computer, your Android phone or tablet, and your TV.',
      altHome: 'Dannify on a computer: Home, with a song playing and its lyrics beside it',
      altSearch: 'Search: what is in your library first, then the top result, songs and artists',
      altLyrics: 'Now Playing with lyrics in time, and the box to line them up with the song',
      altYear: 'Your Soundtrack: your year in music, with your top songs and artists',
      altAlbums: 'The albums in your library, each with its artwork',
      altSpecial: 'Home on Diwali, with its lamps and its music',
      altPhone: 'Dannify on an Android phone, playing a song',
      altTv: 'Dannify on a TV, moved around with the remote',
      allReleases: 'Every release', report: 'Report a problem', support: 'Support Dannify', language: 'Language', yours: 'This device',
      windows: 'Windows', windowsSub: 'Windows 10 and 11',
      windowsHow: ['Open the file once it has downloaded.', 'If Windows says it protected your PC, choose More info, then Run anyway. This is only once.', 'Dannify opens when it is installed.'],
      macos: 'macOS', macosSub: 'macOS 11 and later', appleSilicon: 'Apple silicon (M1 and later)', intel: 'Intel',
      macosHow: ['Open the file and drag Dannify into Applications.', 'The first time, right-click Dannify in Applications and choose Open, then Open again.', 'From then on it opens like any app.'],
      linux: 'Linux', linuxSub: 'Ubuntu, Debian, Mint and the like (64-bit)',
      linuxHow: ['Open the file with your software centre, or run:', '<code>sudo apt install ./{file}</code>', 'Find Dannify among your apps.'],
      android: 'Android', androidSub: 'Phones and tablets, Android 7.0 and later', phones: 'Phones and tablets', emulators: 'Chromebooks and emulators',
      androidHow: ['Open the file once it has downloaded.', 'If your phone asks, let your browser install apps. This is only once.', 'Open Dannify. It keeps itself up to date.'],
      tv: 'TV', tvSub: 'Android TV, Google TV and Fire TV',
      tvHow: ['On the TV, install the Downloader app from its store.', 'In Downloader, go to <code>riskraptor.github.io/Dannify/android</code>', 'Download, install, and move around Dannify with the remote.'],
      iphone: 'Dannify is not on iPhone and iPad yet. Here it is for your other devices.'
    },
    fr: {
      pageTitle: 'Dannify : la musique sur tous vos appareils',
      navFeatures: 'Fonctions', navDownload: 'Télécharger', navAndroid: 'Android', navFaq: 'Questions',
      title: 'Cherchez tout.<br><em>Écoutez-le.</em><br>Gardez-le.',
      lead: 'Un lecteur de musique pour votre ordinateur, votre téléphone et votre TV. Gratuit, sans publicité, et il se met à jour tout seul.',
      getAll: 'Télécharger Dannify', getFor: 'Télécharger pour {p}', version: 'Version {v} · {size}',
      otherMac: 'Mac avec processeur Intel ? <a href="{url}">Prenez celui-ci</a>.',
      otherPlatforms: 'Un autre appareil ? <a href="#download">Tous les téléchargements</a>',
      howTitle: 'Comment l’installer',
      runsOn: 'Dannify fonctionne sur', tWin: '10 et 11', tMac: 'Apple silicon et Intel', notYet: 'Pas encore',
      andEyebrow: 'Téléphones, tablettes et TV', andTitle: 'Dannify pour Android',
      andSub: 'Le même Dannify sur votre téléphone, votre tablette et votre TV. Gratuit, sans publicité, et là aussi il se met à jour tout seul.',
      and7: 'Android 7.0 et plus récent',
      andPerks: ['Un widget pour votre écran d’accueil', 'Sur l’écran de verrouillage et dans la notification', 'Les boutons de vos écouteurs fonctionnent aussi', 'Aussi à l’aise sur une tablette'],
      andScan: 'Sur un ordinateur ? Scannez ceci avec l’appareil photo de votre téléphone pour y installer Dannify.',
      tvRemote: 'Se pilote avec la télécommande',
      tv64: 'Dannify demande une TV ou une clé 64 bits. Beaucoup de clés plus anciennes sont en 32 bits et ne peuvent pas encore le faire tourner.',
      featuresTitle: 'Toute la musique, dans une seule appli', featuresSub: 'Le même Dannify sur votre ordinateur, votre téléphone et votre TV.',
      f1: 'Tout écouter, tout de suite', f1t: 'Cherchez dans tout le catalogue et écoutez en un instant. Tops et nouveautés près de chez vous, ambiances et genres.',
      f1x: 'Un titre démarre en un tiers de seconde environ, et ce qui est déjà dans votre bibliothèque vient en premier.',
      f2: 'Gardez ce que vous aimez', f2t: 'Les titres enregistrés gardent pochette, infos et paroles, et jouent sans connexion.',
      f2x: 'À l’aise hors connexion, et Dannify reprend là où vous vous étiez arrêté, à la seconde près.',
      f3: 'Des paroles en rythme', f3t: 'Les mots s’allument au fil du chant. Absentes ou décalées ? Corrigez-les, et tout le monde en profite.',
      f3x: 'En avance ou en retard ? Cliquez sur la ligne que vous entendez et les mots se calent. Un titre sans paroles ? Écrivez-les et tapez le rythme.',
      f4: 'Écouter ensemble', f4t: 'Créez un salon, partagez son code, et tout le monde entend le même titre au même instant. Discussion et réactions comprises.',
      f4x: 'Les invités peuvent aussi proposer des titres, chacun sur son appareil. Gratuit, sans compte.',
      f5: 'Votre musique, racontée', f5t: 'Historique, statistiques, mix qui suivent vos goûts, et votre année en musique.',
      f5x: 'Aujourd’hui, cette semaine, ce mois-ci et cette année d’un coup d’œil, avec vos séries et les artistes que vous écoutez le plus.',
      f6: 'Collez un lien', f6t: 'Un titre, un album, une playlist ou un artiste Spotify s’ouvre prêt à écouter et à garder.',
      f7: 'Les jours de fête, où que vous soyez',
      f7t: 'Le Nouvel An, le Ramadan et l’Aïd, Diwali, Noël et bien d’autres, aux dates de votre pays. Chacun avec son propre style et sa propre musique.',
      moreTitle: 'Et aussi',
      fDesk: 'Chez lui sur votre ordinateur', fDeskT: 'Une vraie fenêtre, une icône dans la zone de notification, et les touches multimédia de votre clavier.',
      fLang: 'Six langues',
      fUpd: 'À jour tout seul', fUpdT: 'Installez-le une fois. Chaque mise à jour est vérifiée avec la signature de Dannify avant d’être installée.',
      fLight: 'Sombre ou clair', fLightT: 'Un thème sombre et un thème clair. Choisissez celui qui vous plaît.',
      fFree: 'Gratuit, sans publicité', fFreeT: 'Pas de publicité, et pas besoin de compte pour chercher et écouter.',
      dlTitle: 'Télécharger', dlSub: 'Un fichier par appareil. Dannify se met à jour tout seul ensuite.',
      note: 'Chaque fichier est signé par Dannify, et l’appli vérifie la signature de chaque mise à jour. Pas encore sur iPhone et iPad.',
      faqTitle: 'Questions',
      q1: 'Dannify est-il gratuit ?', a1: 'Oui. Gratuit à télécharger et à utiliser, sans publicité.',
      q2: 'Se met-il à jour tout seul ?', a2: 'Oui. Vous installez Dannify une fois ; ensuite, chaque copie se tient à jour toute seule.',
      q3: 'Est-ce sûr ?', a3: 'Chaque fichier est signé par Dannify, et l’appli vérifie la signature de chaque mise à jour avant de l’installer.',
      q4: 'Windows dit avoir protégé mon PC', a4: 'Choisissez Informations complémentaires, puis Exécuter quand même. Windows ne le demande que la première fois.',
      q5: 'Mon Mac dit que Dannify ne peut pas être ouvert',
      a5: 'Clic droit sur Dannify dans Applications, choisissez Ouvrir, puis Ouvrir encore. Sur macOS 15 et plus récent : ouvrez Dannify et fermez le message, puis dans Réglages Système, Confidentialité et sécurité, cliquez sur Ouvrir quand même.',
      q6: 'Mon téléphone dit que Play Protect ne connaît pas l’appli', a6: 'Touchez Plus de détails, puis Installer quand même.',
      q7: 'Fonctionnera-t-il sur ma clé TV ?', a7: 'Si elle est en 64 bits, oui. Beaucoup de clés plus anciennes sont en 32 bits et ne peuvent pas encore faire tourner Dannify.',
      q8: 'Dannify existe-t-il pour iPhone ou iPad ?', a8: 'Pas encore, désolé. En attendant, profitez de Dannify sur votre ordinateur, votre téléphone ou tablette Android, et votre TV.',
      altHome: 'Dannify sur un ordinateur : l’accueil, avec un titre en cours et ses paroles à côté',
      altSearch: 'La recherche : votre bibliothèque d’abord, puis le meilleur résultat, les titres et les artistes',
      altLyrics: 'La lecture en cours, avec les paroles en rythme et la fenêtre pour les caler sur le titre',
      altYear: 'Votre bande-son : votre année en musique, avec vos titres et artistes préférés',
      altAlbums: 'Les albums de votre bibliothèque, chacun avec sa pochette',
      altSpecial: 'L’accueil pour Diwali, avec ses lampes et sa musique',
      altPhone: 'Dannify sur un téléphone Android, en train de jouer un titre',
      altTv: 'Dannify sur une TV, piloté avec la télécommande',
      allReleases: 'Toutes les versions', report: 'Signaler un problème', support: 'Soutenir Dannify', language: 'Langue', yours: 'Cet appareil',
      windows: 'Windows', windowsSub: 'Windows 10 et 11',
      windowsHow: ['Ouvrez le fichier une fois téléchargé.', 'Si Windows dit avoir protégé votre PC, choisissez Informations complémentaires, puis Exécuter quand même. Une seule fois.', 'Dannify s’ouvre une fois installé.'],
      macos: 'macOS', macosSub: 'macOS 11 et plus récent', appleSilicon: 'Apple silicon (M1 et plus)', intel: 'Intel',
      macosHow: ['Ouvrez le fichier et glissez Dannify dans Applications.', 'La première fois, clic droit sur Dannify dans Applications, Ouvrir, puis Ouvrir encore.', 'Ensuite il s’ouvre comme toute appli.'],
      linux: 'Linux', linuxSub: 'Ubuntu, Debian, Mint et autres (64 bits)',
      linuxHow: ['Ouvrez le fichier avec votre logithèque, ou lancez :', '<code>sudo apt install ./{file}</code>', 'Dannify est parmi vos applis.'],
      android: 'Android', androidSub: 'Téléphones et tablettes, Android 7.0 et plus', phones: 'Téléphones et tablettes', emulators: 'Chromebooks et émulateurs',
      androidHow: ['Ouvrez le fichier une fois téléchargé.', 'Si votre téléphone le demande, autorisez votre navigateur à installer des applis. Une seule fois.', 'Ouvrez Dannify. Il se met à jour tout seul.'],
      tv: 'TV', tvSub: 'Android TV, Google TV et Fire TV',
      tvHow: ['Sur la TV, installez l’appli Downloader depuis sa boutique.', 'Dans Downloader, allez à <code>riskraptor.github.io/Dannify/android</code>', 'Téléchargez, installez, et utilisez Dannify avec la télécommande.'],
      iphone: 'Dannify n’est pas encore sur iPhone et iPad. Le voici pour vos autres appareils.'
    },
    es: {
      pageTitle: 'Dannify: música en todos tus dispositivos',
      navFeatures: 'Funciones', navDownload: 'Descargar', navAndroid: 'Android', navFaq: 'Preguntas',
      title: 'Busca lo que quieras.<br><em>Escúchalo ya.</em><br>Guárdalo.',
      lead: 'Un reproductor de música para tu ordenador, tu teléfono y tu TV. Gratis, sin anuncios, y se actualiza solo.',
      getAll: 'Descargar Dannify', getFor: 'Descargar para {p}', version: 'Versión {v} · {size}',
      otherMac: '¿Mac con procesador Intel? <a href="{url}">Descarga ese</a>.',
      otherPlatforms: '¿Otro dispositivo? <a href="#download">Todas las descargas</a>',
      howTitle: 'Cómo instalarlo',
      runsOn: 'Dannify funciona en', tWin: '10 y 11', tMac: 'Apple silicon e Intel', notYet: 'Todavía no',
      andEyebrow: 'Teléfonos, tabletas y TV', andTitle: 'Dannify para Android',
      andSub: 'El mismo Dannify en tu teléfono, tu tableta y tu TV. Gratis, sin anuncios, y también ahí se actualiza solo.',
      and7: 'Android 7.0 o posterior',
      andPerks: ['Un widget para tu pantalla de inicio', 'En la pantalla de bloqueo y en la notificación', 'Los botones de tus auriculares también funcionan', 'Cómodo también en una tableta'],
      andScan: '¿En un ordenador? Escanea esto con la cámara de tu teléfono para tener Dannify allí.',
      tvRemote: 'Se maneja con el mando',
      tv64: 'Dannify necesita una TV o un stick de 64 bits. Muchos sticks antiguos son de 32 bits y todavía no pueden usarlo.',
      featuresTitle: 'Toda la música, en una app', featuresSub: 'El mismo Dannify en tu ordenador, tu teléfono y tu TV.',
      f1: 'Escucha lo que sea, al momento', f1t: 'Busca en todo el catálogo y escucha en un instante. Listas y novedades de donde estás, ambientes y géneros.',
      f1x: 'Una canción empieza en un tercio de segundo, más o menos, y lo que ya está en tu biblioteca sale primero.',
      f2: 'Guarda lo que te gusta', f2t: 'Las canciones guardadas llevan su portada, datos y letra, y suenan sin conexión.',
      f2x: 'Sin conexión, sin problema, y Dannify sigue donde lo dejaste, al segundo.',
      f3: 'Letras al ritmo', f3t: 'Las palabras se iluminan al cantarse. ¿Faltan o van desfasadas? Corrígelas y todos lo notan.',
      f3x: '¿Van adelantadas o atrasadas? Haz clic en la línea que oyes y las palabras se ajustan. ¿Una canción sin letra? Escríbela y marca el ritmo.',
      f4: 'Escuchar juntos', f4t: 'Crea una sala, comparte su código y todos oyen la misma canción a la vez. Con chat y reacciones.',
      f4x: 'Los invitados también pueden sugerir canciones, cada uno en su dispositivo. Gratis y sin cuenta.',
      f5: 'Tu música, contada', f5t: 'Historial, estadísticas, mezclas que te siguen y tu año en música como una historia.',
      f5x: 'Hoy, esta semana, este mes y este año de un vistazo, con tus rachas y los artistas que más escuchas.',
      f6: 'Pega un enlace', f6t: 'Una canción, álbum, lista o artista de Spotify se abre listo para escuchar y guardar.',
      f7: 'Días especiales, estés donde estés',
      f7t: 'Año Nuevo, Ramadán y Eid, Diwali, Navidad y muchos más, en las fechas de tu país. Cada uno con su propio aspecto y su propia música.',
      moreTitle: 'Y más',
      fDesk: 'Como en casa en tu ordenador', fDeskT: 'Una ventana de verdad, un icono en la bandeja del sistema y las teclas multimedia de tu teclado.',
      fLang: 'Seis idiomas',
      fUpd: 'Al día por sí solo', fUpdT: 'Instálalo una vez. Cada actualización se comprueba con la firma de Dannify antes de instalarse.',
      fLight: 'Oscuro o claro', fLightT: 'Un aspecto oscuro y uno claro. Elige el que te guste.',
      fFree: 'Gratis, sin anuncios', fFreeT: 'Sin anuncios, y sin cuenta para buscar y escuchar.',
      dlTitle: 'Descargar', dlSub: 'Un archivo por dispositivo. Después, Dannify se actualiza solo.',
      note: 'Cada archivo está firmado por Dannify, y la app comprueba la firma de cada actualización. Aún no está en iPhone ni iPad.',
      faqTitle: 'Preguntas',
      q1: '¿Dannify es gratis?', a1: 'Sí. Gratis para descargar y usar, sin anuncios.',
      q2: '¿Se actualiza solo?', a2: 'Sí. Instalas Dannify una vez; después, cada copia se mantiene al día sola.',
      q3: '¿Es seguro?', a3: 'Cada archivo está firmado por Dannify, y la app comprueba la firma de cada actualización antes de instalarla.',
      q4: 'Windows dice que protegió mi PC', a4: 'Elige Más información y luego Ejecutar de todas formas. Windows solo lo pregunta la primera vez.',
      q5: 'Mi Mac dice que no se puede abrir Dannify',
      a5: 'Haz clic derecho en Dannify en Aplicaciones, elige Abrir y luego Abrir otra vez. En macOS 15 o posterior: abre Dannify y cierra el aviso; luego, en Ajustes del Sistema, Privacidad y seguridad, haz clic en Abrir igualmente.',
      q6: 'Mi teléfono dice que Play Protect no conoce la app', a6: 'Toca Más detalles y luego Instalar de todas formas.',
      q7: '¿Funcionará en mi stick de TV?', a7: 'Si es de 64 bits, sí. Muchos sticks antiguos son de 32 bits y todavía no pueden usar Dannify.',
      q8: '¿Hay Dannify para iPhone o iPad?', a8: 'Todavía no, lo sentimos. Mientras tanto, disfruta Dannify en tu ordenador, tu teléfono o tableta Android y tu TV.',
      altHome: 'Dannify en un ordenador: Inicio, con una canción sonando y su letra al lado',
      altSearch: 'Búsqueda: primero lo de tu biblioteca, luego el mejor resultado, canciones y artistas',
      altLyrics: 'Reproduciendo, con la letra al ritmo y el cuadro para ajustarla a la canción',
      altYear: 'Tu banda sonora: tu año en música, con tus canciones y artistas favoritos',
      altAlbums: 'Los álbumes de tu biblioteca, cada uno con su portada',
      altSpecial: 'Inicio en Diwali, con sus lámparas y su música',
      altPhone: 'Dannify en un teléfono Android, reproduciendo una canción',
      altTv: 'Dannify en una TV, manejado con el mando',
      allReleases: 'Todas las versiones', report: 'Informar de un problema', support: 'Apoyar a Dannify', language: 'Idioma', yours: 'Este dispositivo',
      windows: 'Windows', windowsSub: 'Windows 10 y 11',
      windowsHow: ['Abre el archivo cuando termine de descargarse.', 'Si Windows dice que protegió tu PC, elige Más información y luego Ejecutar de todas formas. Solo una vez.', 'Dannify se abre al instalarse.'],
      macos: 'macOS', macosSub: 'macOS 11 o posterior', appleSilicon: 'Apple silicon (M1 o posterior)', intel: 'Intel',
      macosHow: ['Abre el archivo y arrastra Dannify a Aplicaciones.', 'La primera vez, clic derecho en Dannify en Aplicaciones, Abrir, y Abrir otra vez.', 'Después se abre como cualquier app.'],
      linux: 'Linux', linuxSub: 'Ubuntu, Debian, Mint y similares (64 bits)',
      linuxHow: ['Abre el archivo con tu centro de software, o ejecuta:', '<code>sudo apt install ./{file}</code>', 'Busca Dannify entre tus apps.'],
      android: 'Android', androidSub: 'Teléfonos y tabletas, Android 7.0 o posterior', phones: 'Teléfonos y tabletas', emulators: 'Chromebooks y emuladores',
      androidHow: ['Abre el archivo cuando termine de descargarse.', 'Si tu teléfono lo pide, deja que tu navegador instale apps. Solo una vez.', 'Abre Dannify. Se actualiza solo.'],
      tv: 'TV', tvSub: 'Android TV, Google TV y Fire TV',
      tvHow: ['En la TV, instala la app Downloader desde su tienda.', 'En Downloader, ve a <code>riskraptor.github.io/Dannify/android</code>', 'Descarga, instala y usa Dannify con el mando.'],
      iphone: 'Dannify aún no está en iPhone ni iPad. Aquí lo tienes para tus otros dispositivos.'
    },
    pt: {
      pageTitle: 'Dannify: música em todos os seus aparelhos',
      navFeatures: 'Recursos', navDownload: 'Baixar', navAndroid: 'Android', navFaq: 'Perguntas',
      title: 'Busque o que quiser.<br><em>Ouça agora.</em><br>Guarde.',
      lead: 'Um player de música para seu computador, celular e TV. Grátis, sem anúncios, e se atualiza sozinho.',
      getAll: 'Baixar o Dannify', getFor: 'Baixar para {p}', version: 'Versão {v} · {size}',
      otherMac: 'Mac com processador Intel? <a href="{url}">Baixe este</a>.',
      otherPlatforms: 'Outro aparelho? <a href="#download">Todos os downloads</a>',
      howTitle: 'Como instalar',
      runsOn: 'O Dannify funciona em', tWin: '10 e 11', tMac: 'Apple silicon e Intel', notYet: 'Ainda não',
      andEyebrow: 'Celulares, tablets e TVs', andTitle: 'Dannify para Android',
      andSub: 'O mesmo Dannify no celular, no tablet e na TV. Grátis, sem anúncios, e lá também se atualiza sozinho.',
      and7: 'Android 7.0 ou mais novo',
      andPerks: ['Um widget para a tela inicial', 'Na tela de bloqueio e na notificação', 'Os botões do seu fone também funcionam', 'À vontade num tablet também'],
      andScan: 'Num computador? Leia isto com a câmera do celular para ter o Dannify nele.',
      tvRemote: 'Usado com o controle remoto',
      tv64: 'O Dannify precisa de uma TV ou stick de 64 bits. Muitos sticks mais antigos são de 32 bits e ainda não conseguem rodá-lo.',
      featuresTitle: 'Toda a música, num app só', featuresSub: 'O mesmo Dannify no computador, no celular e na TV.',
      f1: 'Ouça qualquer coisa, na hora', f1t: 'Pesquise o catálogo inteiro e ouça num instante. Paradas e lançamentos onde você está, climas e gêneros.',
      f1x: 'Uma música começa em cerca de um terço de segundo, e o que já está na sua biblioteca vem primeiro.',
      f2: 'Guarde o que ama', f2t: 'As músicas salvas vêm com capa, dados e letra, e tocam sem conexão.',
      f2x: 'Tranquilo sem conexão, e o Dannify continua de onde você parou, no segundo exato.',
      f3: 'Letras no ritmo', f3t: 'As palavras acendem quando cantadas. Faltando ou fora do tempo? Corrija, e todos recebem.',
      f3x: 'Adiantada ou atrasada? Clique na linha que você ouve e as palavras se alinham. Música sem letra? Escreva e marque o tempo.',
      f4: 'Ouvir juntos', f4t: 'Crie uma sala, compartilhe o código, e todos ouvem a mesma música no mesmo instante. Com chat e reações.',
      f4x: 'Os convidados também podem sugerir músicas, cada um no seu aparelho. Grátis e sem conta.',
      f5: 'Sua música, contada', f5t: 'Histórico, estatísticas, mixes que acompanham você e seu ano em música como uma história.',
      f5x: 'Hoje, esta semana, este mês e este ano num relance, com suas sequências e os artistas que você mais ouve.',
      f6: 'Cole um link', f6t: 'Uma música, álbum, playlist ou artista do Spotify abre pronto para ouvir e guardar.',
      f7: 'Datas especiais, onde você estiver',
      f7t: 'Ano Novo, Ramadã e Eid, Diwali, Natal e muitas outras, nas datas do seu país. Cada uma com seu próprio visual e sua própria música.',
      moreTitle: 'E mais',
      fDesk: 'Em casa no computador', fDeskT: 'Uma janela de verdade, um ícone na bandeja do sistema e as teclas de mídia do teclado.',
      fLang: 'Seis idiomas',
      fUpd: 'Sempre atualizado', fUpdT: 'Instale uma vez. Cada atualização é conferida com a assinatura do Dannify antes de entrar.',
      fLight: 'Escuro ou claro', fLightT: 'Um visual escuro e um claro. Escolha o que preferir.',
      fFree: 'Grátis, sem anúncios', fFreeT: 'Sem anúncios, e sem conta para buscar e ouvir.',
      dlTitle: 'Baixar', dlSub: 'Um arquivo por aparelho. Depois, o Dannify se atualiza sozinho.',
      note: 'Cada arquivo é assinado pelo Dannify, e o app confere a assinatura de cada atualização. Ainda não há para iPhone e iPad.',
      faqTitle: 'Perguntas',
      q1: 'O Dannify é grátis?', a1: 'Sim. Grátis para baixar e usar, sem anúncios.',
      q2: 'Ele se atualiza sozinho?', a2: 'Sim. Você instala o Dannify uma vez; depois, cada cópia se mantém atualizada sozinha.',
      q3: 'É seguro?', a3: 'Cada arquivo é assinado pelo Dannify, e o app confere a assinatura de cada atualização antes de instalá-la.',
      q4: 'O Windows diz que protegeu meu PC', a4: 'Escolha Mais informações e depois Executar assim mesmo. O Windows só pergunta na primeira vez.',
      q5: 'Meu Mac diz que o Dannify não pode ser aberto',
      a5: 'Clique com o botão direito no Dannify em Aplicativos, escolha Abrir e depois Abrir de novo. No macOS 15 ou mais novo: abra o Dannify e feche o aviso; depois, em Ajustes do Sistema, Privacidade e Segurança, clique em Abrir Mesmo Assim.',
      q6: 'Meu celular diz que o Play Protect não conhece o app', a6: 'Toque em Mais detalhes e depois em Instalar mesmo assim.',
      q7: 'Vai rodar no meu stick de TV?', a7: 'Se for de 64 bits, sim. Muitos sticks mais antigos são de 32 bits e ainda não rodam o Dannify.',
      q8: 'Tem Dannify para iPhone ou iPad?', a8: 'Ainda não, desculpe. Por enquanto, aproveite o Dannify no computador, no celular ou tablet Android e na TV.',
      altHome: 'O Dannify num computador: Início, com uma música tocando e a letra ao lado',
      altSearch: 'Busca: primeiro o que está na sua biblioteca, depois o melhor resultado, músicas e artistas',
      altLyrics: 'Tocando agora, com a letra no ritmo e a caixa para alinhá-la com a música',
      altYear: 'Sua trilha sonora: seu ano em música, com suas músicas e artistas favoritos',
      altAlbums: 'Os álbuns da sua biblioteca, cada um com sua capa',
      altSpecial: 'O Início no Diwali, com suas lamparinas e sua música',
      altPhone: 'O Dannify num celular Android, tocando uma música',
      altTv: 'O Dannify numa TV, usado com o controle remoto',
      allReleases: 'Todas as versões', report: 'Relatar um problema', support: 'Apoiar o Dannify', language: 'Idioma', yours: 'Este aparelho',
      windows: 'Windows', windowsSub: 'Windows 10 e 11',
      windowsHow: ['Abra o arquivo quando terminar de baixar.', 'Se o Windows disser que protegeu o PC, escolha Mais informações e depois Executar assim mesmo. Só uma vez.', 'O Dannify abre quando estiver instalado.'],
      macos: 'macOS', macosSub: 'macOS 11 ou mais novo', appleSilicon: 'Apple silicon (M1 ou mais novo)', intel: 'Intel',
      macosHow: ['Abra o arquivo e arraste o Dannify para Aplicativos.', 'Na primeira vez, clique com o botão direito no Dannify em Aplicativos, Abrir, e Abrir de novo.', 'Depois ele abre como qualquer app.'],
      linux: 'Linux', linuxSub: 'Ubuntu, Debian, Mint e afins (64 bits)',
      linuxHow: ['Abra o arquivo na central de programas, ou rode:', '<code>sudo apt install ./{file}</code>', 'Ache o Dannify entre seus apps.'],
      android: 'Android', androidSub: 'Celulares e tablets, Android 7.0 ou mais novo', phones: 'Celulares e tablets', emulators: 'Chromebooks e emuladores',
      androidHow: ['Abra o arquivo quando terminar de baixar.', 'Se o celular pedir, deixe o navegador instalar apps. Só uma vez.', 'Abra o Dannify. Ele se atualiza sozinho.'],
      tv: 'TV', tvSub: 'Android TV, Google TV e Fire TV',
      tvHow: ['Na TV, instale o app Downloader pela loja.', 'No Downloader, vá a <code>riskraptor.github.io/Dannify/android</code>', 'Baixe, instale e use o Dannify com o controle.'],
      iphone: 'O Dannify ainda não está no iPhone e iPad. Aqui está para seus outros aparelhos.'
    },
    de: {
      pageTitle: 'Dannify: Musik auf jedem Gerät',
      navFeatures: 'Funktionen', navDownload: 'Herunterladen', navAndroid: 'Android', navFaq: 'Fragen',
      title: 'Alles suchen.<br><em>Sofort hören.</em><br>Behalten.',
      lead: 'Ein Musikplayer für Computer, Telefon und Fernseher. Kostenlos, ohne Werbung, und er hält sich selbst aktuell.',
      getAll: 'Dannify herunterladen', getFor: 'Für {p} herunterladen', version: 'Version {v} · {size}',
      otherMac: 'Mac mit Intel-Prozessor? <a href="{url}">Diese Version</a>.',
      otherPlatforms: 'Ein anderes Gerät? <a href="#download">Alle Downloads</a>',
      howTitle: 'So installieren Sie es',
      runsOn: 'Dannify läuft auf', tWin: '10 und 11', tMac: 'Apple Silicon und Intel', notYet: 'Noch nicht',
      andEyebrow: 'Telefone, Tablets und Fernseher', andTitle: 'Dannify für Android',
      andSub: 'Dasselbe Dannify auf Telefon, Tablet und Fernseher. Kostenlos, ohne Werbung, und auch dort hält es sich selbst aktuell.',
      and7: 'Android 7.0 und neuer',
      andPerks: ['Ein Widget für den Startbildschirm', 'Auf dem Sperrbildschirm und in der Benachrichtigung', 'Die Tasten Ihrer Kopfhörer spielen mit', 'Auch auf dem Tablet zu Hause'],
      andScan: 'Am Computer? Scannen Sie dies mit der Kamera Ihres Telefons, um Dannify dort zu bekommen.',
      tvRemote: 'Bedient mit der Fernbedienung',
      tv64: 'Dannify braucht einen 64-Bit-Fernseher oder -Stick. Viele ältere Sticks sind 32-Bit und können es noch nicht ausführen.',
      featuresTitle: 'Alles für Musik, in einer App', featuresSub: 'Dasselbe Dannify auf Computer, Telefon und Fernseher.',
      f1: 'Alles hören, sofort', f1t: 'Den ganzen Katalog durchsuchen und im Nu abspielen. Charts und Neues aus Ihrer Gegend, Stimmungen und Genres.',
      f1x: 'Ein Titel startet in etwa einer Drittelsekunde, und was schon in Ihrer Bibliothek ist, kommt zuerst.',
      f2: 'Behalten, was Sie lieben', f2t: 'Gespeicherte Titel kommen mit Cover, Angaben und Songtext und spielen ohne Verbindung.',
      f2x: 'Auch offline entspannt, und Dannify macht dort weiter, wo Sie aufgehört haben, auf die Sekunde.',
      f3: 'Songtexte im Takt', f3t: 'Die Wörter leuchten beim Singen auf. Fehlen sie oder sind sie verschoben? Korrigieren, und alle haben es.',
      f3x: 'Zu früh oder zu spät? Klicken Sie auf die Zeile, die Sie hören, und die Wörter passen. Ein Titel ohne Text? Schreiben Sie ihn und tippen Sie den Takt ein.',
      f4: 'Zusammen hören', f4t: 'Raum starten, Code teilen, und alle hören denselben Titel im selben Moment. Mit Chat und Reaktionen.',
      f4x: 'Gäste können auch Titel vorschlagen, jeder auf seinem eigenen Gerät. Kostenlos, ohne Konto.',
      f5: 'Ihre Musik, erzählt', f5t: 'Verlauf, Statistik, Mixe, die mit Ihnen gehen, und Ihr Musikjahr als Geschichte.',
      f5x: 'Heute, diese Woche, diesen Monat und dieses Jahr auf einen Blick, mit Ihren Serien und den Künstlern, die Sie am meisten hören.',
      f6: 'Link einfügen', f6t: 'Ein Spotify-Titel, -Album, -Playlist oder -Künstler öffnet sich bereit zum Hören und Speichern.',
      f7: 'Besondere Tage, wo immer Sie sind',
      f7t: 'Neujahr, Ramadan und Eid, Diwali, Weihnachten und viele mehr, an den Daten Ihres Landes. Jeder mit eigenem Aussehen und eigener Musik.',
      moreTitle: 'Und mehr',
      fDesk: 'Zu Hause auf Ihrem Computer', fDeskT: 'Ein echtes Fenster, ein Symbol im Infobereich und die Medientasten Ihrer Tastatur.',
      fLang: 'Sechs Sprachen',
      fUpd: 'Von selbst aktuell', fUpdT: 'Einmal installieren. Jedes Update wird vor der Installation mit der Signatur von Dannify geprüft.',
      fLight: 'Dunkel oder hell', fLightT: 'Ein dunkles und ein helles Aussehen. Wählen Sie, was Ihnen gefällt.',
      fFree: 'Kostenlos, ohne Werbung', fFreeT: 'Keine Werbung, und kein Konto nötig, um zu suchen und zu hören.',
      dlTitle: 'Herunterladen', dlSub: 'Eine Datei pro Gerät. Danach hält sich Dannify selbst aktuell.',
      note: 'Jede Datei ist von Dannify signiert, und die App prüft die Signatur jedes Updates. Noch nicht für iPhone und iPad.',
      faqTitle: 'Fragen',
      q1: 'Ist Dannify kostenlos?', a1: 'Ja. Kostenlos herunterzuladen und zu nutzen, ohne Werbung.',
      q2: 'Aktualisiert es sich selbst?', a2: 'Ja. Sie installieren Dannify einmal; danach hält sich jede Kopie selbst aktuell.',
      q3: 'Ist es sicher?', a3: 'Jede Datei ist von Dannify signiert, und die App prüft die Signatur jedes Updates, bevor sie es installiert.',
      q4: 'Windows meldet, es habe meinen PC geschützt', a4: 'Wählen Sie Weitere Informationen, dann Trotzdem ausführen. Windows fragt nur beim ersten Mal.',
      q5: 'Mein Mac sagt, Dannify kann nicht geöffnet werden',
      a5: 'Klicken Sie in Programme mit der rechten Maustaste auf Dannify, wählen Sie Öffnen und dann nochmals Öffnen. Ab macOS 15: Öffnen Sie Dannify und schließen Sie die Meldung, dann klicken Sie in Systemeinstellungen, Datenschutz & Sicherheit, auf Dennoch öffnen.',
      q6: 'Mein Telefon sagt, Play Protect kennt die App nicht', a6: 'Tippen Sie auf Weitere Details, dann auf Trotzdem installieren.',
      q7: 'Läuft es auf meinem TV-Stick?', a7: 'Wenn er 64-Bit hat, ja. Viele ältere Sticks sind 32-Bit und können Dannify noch nicht ausführen.',
      q8: 'Gibt es Dannify für iPhone oder iPad?', a8: 'Noch nicht, leider. Bis dahin genießen Sie Dannify auf Ihrem Computer, Ihrem Android-Telefon oder -Tablet und Ihrem Fernseher.',
      altHome: 'Dannify auf einem Computer: die Startseite, mit einem laufenden Titel und seinem Text daneben',
      altSearch: 'Die Suche: zuerst Ihre Bibliothek, dann das beste Ergebnis, Titel und Künstler',
      altLyrics: 'Die Wiedergabe, mit Songtext im Takt und dem Feld, um ihn an den Titel anzupassen',
      altYear: 'Ihr Soundtrack: Ihr Musikjahr, mit Ihren liebsten Titeln und Künstlern',
      altAlbums: 'Die Alben in Ihrer Bibliothek, jedes mit seinem Cover',
      altSpecial: 'Die Startseite zu Diwali, mit ihren Lichtern und ihrer Musik',
      altPhone: 'Dannify auf einem Android-Telefon, beim Abspielen eines Titels',
      altTv: 'Dannify auf einem Fernseher, bedient mit der Fernbedienung',
      allReleases: 'Alle Versionen', report: 'Problem melden', support: 'Dannify unterstützen', language: 'Sprache', yours: 'Dieses Gerät',
      windows: 'Windows', windowsSub: 'Windows 10 und 11',
      windowsHow: ['Öffnen Sie die Datei nach dem Download.', 'Meldet Windows, es habe den PC geschützt: Weitere Informationen, dann Trotzdem ausführen. Nur einmal.', 'Dannify öffnet sich nach der Installation.'],
      macos: 'macOS', macosSub: 'macOS 11 und neuer', appleSilicon: 'Apple Silicon (M1 und neuer)', intel: 'Intel',
      macosHow: ['Öffnen Sie die Datei und ziehen Sie Dannify in Programme.', 'Beim ersten Mal Rechtsklick auf Dannify in Programme, Öffnen, und nochmals Öffnen.', 'Danach öffnet es sich wie jede App.'],
      linux: 'Linux', linuxSub: 'Ubuntu, Debian, Mint und Ähnliche (64-Bit)',
      linuxHow: ['Öffnen Sie die Datei in der Softwareverwaltung, oder führen Sie aus:', '<code>sudo apt install ./{file}</code>', 'Dannify ist unter Ihren Apps.'],
      android: 'Android', androidSub: 'Telefone und Tablets, Android 7.0 und neuer', phones: 'Telefone und Tablets', emulators: 'Chromebooks und Emulatoren',
      androidHow: ['Öffnen Sie die Datei nach dem Download.', 'Fragt das Telefon, erlauben Sie dem Browser, Apps zu installieren. Nur einmal.', 'Öffnen Sie Dannify. Es hält sich selbst aktuell.'],
      tv: 'TV', tvSub: 'Android TV, Google TV und Fire TV',
      tvHow: ['Installieren Sie auf dem Fernseher die App Downloader aus dem Store.', 'Gehen Sie in Downloader zu <code>riskraptor.github.io/Dannify/android</code>', 'Herunterladen, installieren, und Dannify mit der Fernbedienung nutzen.'],
      iphone: 'Dannify gibt es noch nicht für iPhone und iPad. Hier ist es für Ihre anderen Geräte.'
    },
    sw: {
      pageTitle: 'Dannify: muziki kwenye kila kifaa',
      navFeatures: 'Vipengele', navDownload: 'Pakua', navAndroid: 'Android', navFaq: 'Maswali',
      title: 'Tafuta chochote.<br><em>Kicheze sasa.</em><br>Kihifadhi.',
      lead: 'Kicheza muziki cha kompyuta, simu na TV yako. Bure, bila matangazo, na kinajisasisha chenyewe.',
      getAll: 'Pakua Dannify', getFor: 'Pakua kwa {p}', version: 'Toleo {v} · {size}',
      otherMac: 'Mac yenye kichakataji cha Intel? <a href="{url}">Pata hiyo</a>.',
      otherPlatforms: 'Kifaa kingine? <a href="#download">Vipakuliwa vyote</a>',
      howTitle: 'Jinsi ya kusakinisha',
      runsOn: 'Dannify inapatikana kwa', tWin: '10 na 11', tMac: 'Apple silicon na Intel', notYet: 'Bado',
      andEyebrow: 'Simu, tablet na TV', andTitle: 'Dannify kwa Android',
      andSub: 'Dannify ile ile kwenye simu, tablet na TV yako. Bure, bila matangazo, na huko pia inajisasisha yenyewe.',
      and7: 'Android 7.0 na mpya zaidi',
      andPerks: ['Wijeti ya skrini yako ya mwanzo', 'Inacheza kwenye skrini iliyofungwa na kwenye arifa', 'Vitufe vya vipokea sauti vyako vinafanya kazi', 'Inafaa pia kwenye tablet'],
      andScan: 'Uko kwenye kompyuta? Changanua hii kwa kamera ya simu yako upate Dannify huko.',
      tvRemote: 'Inatumika kwa rimoti',
      tv64: 'Dannify inahitaji TV au TV stick ya biti 64. TV stick nyingi za zamani ni biti 32 na bado haziwezi kuiendesha.',
      featuresTitle: 'Muziki wote, katika programu moja', featuresSub: 'Dannify ile ile kwenye kompyuta, simu na TV yako.',
      f1: 'Cheza chochote, papo hapo', f1t: 'Tafuta katalogi nzima na ucheze mara moja. Chati na mapya ulipo, hisia na aina.',
      f1x: 'Wimbo unaanza kwa takriban theluthi ya sekunde, na vilivyo tayari kwenye maktaba yako vinakuja kwanza.',
      f2: 'Hifadhi unachopenda', f2t: 'Nyimbo ulizohifadhi zinakuja na picha, maelezo na maneno, na zinacheza bila mtandao.',
      f2x: 'Inafanya kazi vizuri bila mtandao, na Dannify inaendelea ulipoishia, hadi sekunde.',
      f3: 'Maneno kwa wakati', f3t: 'Maneno yanawaka yanapoimbwa. Hayapo au yamechelewa? Yarekebishe, na wote wanapata.',
      f3x: 'Yanatangulia au yanachelewa? Bofya mstari unaousikia na maneno yanapangika. Wimbo hauna maneno? Yaandike na ugonge muda wake.',
      f4: 'Sikiliza pamoja', f4t: 'Anzisha chumba, shiriki msimbo wake, na wote wanasikia wimbo uleule wakati uleule. Pamoja na gumzo na hisia.',
      f4x: 'Wageni pia wanaweza kupendekeza nyimbo, kila mmoja kwenye kifaa chake. Bure, bila akaunti.',
      f5: 'Muziki wako, ukisimuliwa', f5t: 'Historia, takwimu, mchanganyiko unaokufuata, na mwaka wako wa muziki kama hadithi.',
      f5x: 'Leo, wiki hii, mwezi huu na mwaka huu kwa mtazamo mmoja, pamoja na mfululizo wako na wasanii unaowasikiliza zaidi.',
      f6: 'Bandika kiungo', f6t: 'Wimbo, albamu, orodha au msanii wa Spotify hufunguka tayari kucheza na kuhifadhi.',
      f7: 'Siku maalum, popote ulipo',
      f7t: 'Mwaka Mpya, Ramadhani na Idi, Diwali, Krismasi na nyingine nyingi, kwa tarehe za nchi yako. Kila moja ina mwonekano wake na muziki wake.',
      moreTitle: 'Na zaidi',
      fDesk: 'Nyumbani kwenye kompyuta yako', fDeskT: 'Dirisha halisi, aikoni kwenye trei, na vitufe vya midia vya kibodi yako.',
      fLang: 'Lugha sita',
      fUpd: 'Inajisasisha yenyewe', fUpdT: 'Sakinisha mara moja. Kila sasisho linakaguliwa kwa saini ya Dannify kabla ya kuingia.',
      fLight: 'Giza au mwanga', fLightT: 'Mwonekano wa giza na wa mwanga. Chagua unaoupenda.',
      fFree: 'Bure, bila matangazo', fFreeT: 'Hakuna matangazo, na huhitaji akaunti kutafuta na kucheza.',
      dlTitle: 'Pakua', dlSub: 'Faili moja kwa kila kifaa. Baada ya hapo Dannify inajisasisha yenyewe.',
      note: 'Kila faili limesainiwa na Dannify, na programu inakagua saini ya kila sasisho. Bado haipo kwa iPhone na iPad.',
      faqTitle: 'Maswali',
      q1: 'Je, Dannify ni bure?', a1: 'Ndiyo. Bure kupakua na kutumia, bila matangazo.',
      q2: 'Je, inajisasisha yenyewe?', a2: 'Ndiyo. Unasakinisha Dannify mara moja; baada ya hapo, kila nakala inajisasisha yenyewe.',
      q3: 'Je, ni salama?', a3: 'Kila faili limesainiwa na Dannify, na programu inakagua saini ya kila sasisho kabla ya kulisakinisha.',
      q4: 'Windows inasema imelinda kompyuta yangu', a4: 'Chagua More info, kisha Run anyway. Windows inauliza mara ya kwanza tu.',
      q5: 'Mac yangu inasema Dannify haiwezi kufunguliwa',
      a5: 'Bofya kulia Dannify ndani ya Applications, chagua Open, kisha Open tena. Kwenye macOS 15 na mpya zaidi: fungua Dannify na ubofye Done, kisha ndani ya System Settings, Privacy & Security, bofya Open Anyway.',
      q6: 'Simu yangu inasema Play Protect haiijui programu hii', a6: 'Gusa More details, kisha Install anyway.',
      q7: 'Je, itafanya kazi kwenye TV stick yangu?', a7: 'Ikiwa ni ya biti 64, ndiyo. TV stick nyingi za zamani ni biti 32 na bado haziwezi kuendesha Dannify.',
      q8: 'Je, kuna Dannify kwa iPhone au iPad?', a8: 'Bado, samahani. Kwa sasa, furahia Dannify kwenye kompyuta yako, simu au tablet yako ya Android, na TV yako.',
      altHome: 'Dannify kwenye kompyuta: Mwanzo, wimbo ukicheza na maneno yake pembeni',
      altSearch: 'Utafutaji: vilivyo kwenye maktaba yako kwanza, kisha tokeo bora, nyimbo na wasanii',
      altLyrics: 'Kinachocheza sasa, maneno yakienda na wimbo, na kisanduku cha kuyapanga',
      altYear: 'Wimbo wa mwaka wako: mwaka wako wa muziki, na nyimbo na wasanii unaowapenda zaidi',
      altAlbums: 'Albamu zilizo kwenye maktaba yako, kila moja na picha yake',
      altSpecial: 'Mwanzo wakati wa Diwali, na taa zake na muziki wake',
      altPhone: 'Dannify kwenye simu ya Android, ikicheza wimbo',
      altTv: 'Dannify kwenye TV, ikitumika kwa rimoti',
      allReleases: 'Matoleo yote', report: 'Ripoti tatizo', support: 'Saidia Dannify', language: 'Lugha', yours: 'Kifaa hiki',
      windows: 'Windows', windowsSub: 'Windows 10 na 11',
      windowsHow: ['Fungua faili likishapakuliwa.', 'Windows ikisema imelinda kompyuta yako, chagua More info, kisha Run anyway. Mara moja tu.', 'Dannify inafunguka ikishasakinishwa.'],
      macos: 'macOS', macosSub: 'macOS 11 na mpya zaidi', appleSilicon: 'Apple silicon (M1 na mpya zaidi)', intel: 'Intel',
      macosHow: ['Fungua faili na uburute Dannify hadi Applications.', 'Mara ya kwanza, bofya kulia Dannify ndani ya Applications, Open, kisha Open tena.', 'Baada ya hapo inafunguka kama programu yoyote.'],
      linux: 'Linux', linuxSub: 'Ubuntu, Debian, Mint na kama hizo (biti 64)',
      linuxHow: ['Fungua faili kwa kituo cha programu, au endesha:', '<code>sudo apt install ./{file}</code>', 'Tafuta Dannify kati ya programu zako.'],
      android: 'Android', androidSub: 'Simu na tablet, Android 7.0 na mpya zaidi', phones: 'Simu na tablet', emulators: 'Chromebook na emulator',
      androidHow: ['Fungua faili likishapakuliwa.', 'Simu ikiuliza, ruhusu kivinjari chako kusakinisha programu. Mara moja tu.', 'Fungua Dannify. Inajisasisha yenyewe.'],
      tv: 'TV', tvSub: 'Android TV, Google TV na Fire TV',
      tvHow: ['Kwenye TV, sakinisha programu ya Downloader kutoka duka lake.', 'Ndani ya Downloader, nenda <code>riskraptor.github.io/Dannify/android</code>', 'Pakua, sakinisha, na utumie Dannify kwa rimoti.'],
      iphone: 'Dannify bado haipo kwa iPhone na iPad. Hii hapa kwa vifaa vyako vingine.'
    }
  };

  // The language: ?lang= when it was picked, the browser's otherwise.
  var lang = 'en';
  var picked = '';
  try { picked = String(new URLSearchParams(location.search).get('lang') || '').slice(0, 2).toLowerCase(); } catch (e) { /* none picked */ }
  if (WORDS[picked]) lang = picked;
  else {
    var langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || 'en'];
    for (var i = 0; i < langs.length; i++) {
      var c = String(langs[i]).slice(0, 2).toLowerCase();
      if (WORDS[c]) { lang = c; break; }
    }
  }
  var W = WORDS[lang];
  W.getAndroid = W.getFor.replace('{p}', W.android);
  document.documentElement.lang = lang;
  document.title = W.pageTitle;

  // Steps as list items; an address or a command may break after / . _
  function list(items) {
    return items.map(function (s) {
      return '<li>' + s.replace(/<code>(.*?)<\/code>/g, function (m, c) { return '<code>' + c.replace(/([\/._])/g, '$1<wbr>') + '</code>'; }) + '</li>';
    }).join('');
  }
  function each(selector, fn) { Array.prototype.forEach.call(document.querySelectorAll(selector), fn); }
  each('[data-w]', function (el) {
    var text = W[el.getAttribute('data-w')];
    if (text == null) return;
    if (Array.isArray(text)) el.innerHTML = list(text);
    else if (el.hasAttribute('data-html')) el.innerHTML = text;
    else el.textContent = text;
  });
  each('[data-wa]', function (el) { var t = W[el.getAttribute('data-wa')]; if (t) el.alt = t; });
  each('[data-wl]', function (el) { var t = W[el.getAttribute('data-wl')]; if (t) el.setAttribute('aria-label', t); });
  each('.langs a', function (a) {
    if (a.getAttribute('data-lang') === lang) a.setAttribute('aria-current', 'true');
    a.href = '?lang=' + a.getAttribute('data-lang') + location.hash;
  });

  // Which device this is.
  var ua = navigator.userAgent || '';
  var device = /Android/i.test(ua) && /AFT|BRAVIA|GoogleTV|Android TV|SmartTV|\bTV\b/i.test(ua) ? 'tv'
    : /Android/i.test(ua) ? 'android'
    : /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) ? 'ios'
    : /Macintosh|Mac OS X/.test(ua) ? 'macos'
    : /Windows/.test(ua) ? 'windows'
    : /Linux|X11|CrOS/.test(ua) ? 'linux' : '';
  if (device) document.documentElement.setAttribute('data-device', device);

  // Its tile, marked.
  var tile = device && document.querySelector('.tile[data-device="' + device + '"]');
  if (tile) {
    tile.classList.add('is-yours');
    var here = document.createElement('span');
    here.className = 'here';
    here.textContent = W.yours;
    tile.appendChild(here);
  }

  // A question linked to (the iPhone tile, or a shared link) opens.
  function openQuestion(hash) {
    var q = /^#q-[a-z]+$/.test(hash) && document.getElementById(hash.slice(1));
    if (q && q.tagName === 'DETAILS') q.open = true;
  }
  each('a[href^="#q-"]', function (a) { a.addEventListener('click', function () { openQuestion(a.getAttribute('href')); }); });
  openQuestion(location.hash);
  window.addEventListener('hashchange', function () { openQuestion(location.hash); });

  // A Mac's processor: asked where the browser can say; Apple silicon
  // otherwise (every Mac sold since 2023), with Intel offered beside it.
  var macArch = 'arm64';
  function knowMac(done) {
    if (device !== 'macos') return done();
    try {
      if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
        navigator.userAgentData.getHighEntropyValues(['architecture']).then(function (v) {
          if (v && v.architecture === 'x86') macArch = 'x64';
          done();
        }, done);
        return;
      }
      var gl = document.createElement('canvas').getContext('webgl');
      var dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
      var gpu = dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : '';
      if (/Intel|AMD|Radeon/i.test(gpu) && !/Apple/i.test(gpu)) macArch = 'x64';
    } catch (e) { /* the default stands */ }
    done();
  }

  var RELEASES = 'https://github.com/Riskraptor/Dannify/releases/latest';
  var androidArch = /x86_64|x86-64|Intel/i.test(ua) ? 'x86_64' : 'arm64';
  function esc(s) { return String(s).replace(/[&<>"']/g, function (ch) { return '&#' + ch.charCodeAt(0) + ';'; }); }
  function mb(bytes) { return bytes > 0 ? Math.round(bytes / 1048576) + ' MB' : ''; }
  function pick(files, platform, arch) {
    return files.filter(function (f) { return f.platform === platform && (!arch || f.arch === arch); })[0];
  }
  function steps(items, file) {
    return list(items.map(function (s) { return s.replace('{file}', file ? esc(file.name) : 'linux-dannify_…_amd64.deb'); }));
  }

  // The files: from latest.json beside this page, or from GitHub's API.
  function fromApi(release) {
    var kinds = [[/^Dannify-Setup-.*\.exe$/, 'windows', ''], [/^macos-.*-arm64\.dmg$/, 'macos', 'arm64'], [/^macos-.*-x64\.dmg$/, 'macos', 'x64'],
      [/^linux-.*_amd64\.deb$/, 'linux', 'amd64'], [/^android-.*-arm64\.apk$/, 'android', 'arm64'], [/^android-.*-x86_64\.apk$/, 'android', 'x86_64']];
    var files = [];
    (release.assets || []).forEach(function (a) {
      kinds.forEach(function (k) {
        if (k[0].test(a.name)) files.push({ platform: k[1], arch: k[2], name: a.name, size: a.size, url: a.browser_download_url });
      });
    });
    return { version: String(release.tag_name || '').replace(/^v/, ''), files: files };
  }
  function load() {
    return fetch('latest.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw r; return r.json(); })
      .catch(function () {
        return fetch('https://api.github.com/repos/Riskraptor/Dannify/releases/latest')
          .then(function (r) { if (!r.ok) throw r; return r.json(); })
          .then(fromApi);
      });
  }

  function cardsFor(f) {
    return [
      { id: 'windows', icon: 'i-windows', name: W.windows, sub: W.windowsSub, how: W.windowsHow, links: [{ file: pick(f, 'windows'), label: W.windows }] },
      { id: 'macos', icon: 'i-mac', name: W.macos, sub: W.macosSub, how: W.macosHow, links: [{ file: pick(f, 'macos', macArch), label: macArch === 'x64' ? W.intel : W.appleSilicon }, { file: pick(f, 'macos', macArch === 'x64' ? 'arm64' : 'x64'), label: macArch === 'x64' ? W.appleSilicon : W.intel }] },
      { id: 'linux', icon: 'i-linux', name: W.linux, sub: W.linuxSub, how: W.linuxHow, links: [{ file: pick(f, 'linux'), label: '.deb' }] },
      { id: 'android', icon: 'i-phone', name: W.android, sub: W.androidSub, how: W.androidHow, links: [{ file: pick(f, 'android', 'arm64'), label: W.phones }, { file: pick(f, 'android', 'x86_64'), label: W.emulators }] },
      { id: 'tv', icon: 'i-tv', name: W.tv, sub: W.tvSub, how: W.tvHow, links: [{ file: pick(f, 'android', 'arm64'), label: W.android }] }
    ];
  }

  // Every file, this device's first.
  function renderCards(latest) {
    var cards = cardsFor(latest.files || []);
    var mine = device === 'ios' ? '' : device;
    cards.sort(function (a, b) { return (b.id === mine) - (a.id === mine); });
    var html = '';
    cards.forEach(function (c) {
      var links = c.links.map(function (l, n) {
        if (!l.file && n > 0) return '';
        return '<a class="' + (n === 0 ? 'main' : '') + '" href="' + esc(l.file ? l.file.url : RELEASES) + '">' +
          (n === 0 ? '<svg aria-hidden="true"><use href="#i-dl"/></svg>' : '') + esc(l.label) +
          (l.file ? ' <small>' + mb(l.file.size) + '</small>' : '') + '</a>';
      }).join('');
      html += '<article class="file' + (c.id === mine ? ' is-yours' : '') + '" id="get-' + c.id + '">' +
        '<div class="file-top"><span class="ic" aria-hidden="true"><svg class="i"><use href="#' + c.icon + '"/></svg></span><div><b>' + c.name + '</b><span class="sub">' + c.sub + '</span></div>' +
        (c.id === mine ? '<span class="tag">' + W.yours + '</span>' : '') + '</div>' +
        '<ol class="how">' + steps(c.how, c.links[0].file) + '</ol>' +
        '<div class="dl">' + links + '</div></article>';
    });
    document.getElementById('files').innerHTML = html;
    return cards;
  }

  function render(latest) {
    var f = latest.files || [];
    var cards = renderCards(latest);

    // Dannify for Android: the APK for this phone.
    var apk = pick(f, 'android', device === 'android' || device === 'tv' ? androidArch : 'arm64') || pick(f, 'android');
    if (apk) {
      document.getElementById('getApk').href = apk.url;
      document.getElementById('apkMeta').textContent = W.version.replace('{v}', latest.version).replace('{size}', mb(apk.size));
    }

    // The big button: this device's file, and how to install it.
    var file = device === 'windows' ? pick(f, 'windows')
      : device === 'macos' ? pick(f, 'macos', macArch)
      : device === 'linux' ? pick(f, 'linux')
      : device === 'android' || device === 'tv' ? apk : null;
    var meta = document.getElementById('meta');
    if (!file) {
      meta.textContent = device === 'ios' ? W.iphone : W.version.replace('{v}', latest.version).replace(' · {size}', '');
      if (device === 'ios') document.getElementById('alt').innerHTML = W.otherPlatforms;
      return;
    }
    var card = cards.filter(function (c) { return c.id === device; })[0];
    document.getElementById('get').href = file.url;
    document.getElementById('getWords').textContent = W.getFor.replace('{p}', card.name);
    meta.textContent = W.version.replace('{v}', latest.version).replace('{size}', mb(file.size));
    document.getElementById('how').innerHTML = steps(card.how, file);
    document.getElementById('install').hidden = false;
    var intel = pick(f, 'macos', 'x64');
    document.getElementById('alt').innerHTML =
      device === 'macos' && macArch === 'arm64' && intel ? W.otherMac.replace('{url}', esc(intel.url)) : W.otherPlatforms;
  }

  // The cards at once (so links to them work), their files when known.
  renderCards({ files: [] });
  if (device === 'ios') document.getElementById('meta').textContent = W.iphone;
  knowMac(function () {
    load().then(render).catch(function () {
      document.getElementById('get').href = RELEASES;
    });
  });
})();
