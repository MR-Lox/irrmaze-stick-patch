# Irritating Maze : patch stick arcade

Patch IPS pour jouer à **The Irritating Maze** (*Ultra Denryū Iraira Bō*, SNK/Saurus, 1997, Neo Geo MVS) avec un **stick Neo Geo standard** au lieu du trackball.

Le jeu n'a jamais été prévu pour autre chose que son trackball. Or plus aucun trackball compatible Neo Geo n'est fabriqué : sans ce patch, une cartouche est injouable sur une borne MVS classique.

> ⚠️ Ce dépôt ne contient **aucune ROM**. Il fournit seulement des patchs IPS et le script qui les génère. Il te faut ton propre dump du jeu.

## Commandes

| Stick | Effet |
|---|---|
| Directions | Déplacent la tige : 1 px/frame dès l'appui, puis accélération progressive jusqu'à 3 px/frame (~1 s) |
| **A** | Bouton 1 du jeu (valider, revoir le parcours en le maintenant) |
| **B** | Bouton 2 du jeu |
| **C** maintenu | Mode précision (~0,4 px/frame), pour les passages étroits |
| **D** maintenu | Mode rapide (4 px/frame) |

Les sticks J1 et J2 pilotent tous les deux la tige, ce qui sert pour jouer à deux en alternance.

## Appliquer le patch

Le patch ne modifie que la ROM programme `236-p1`. Il en existe deux formats selon l'âge du romset, d'où deux fichiers :

| Patch | ROM d'origine attendue | CRC32 après patch |
|---|---|---|
| [`patches/irrmaze_stick.ips`](patches/irrmaze_stick.ips) | `236-p1.p1`, set MAME actuel, CRC32 `4C2FF660` | `36D9A5C8` |
| [`patches/irrmaze_stick_ancien_format.ips`](patches/irrmaze_stick_ancien_format.ips) | `236-p1.bin`, anciens sets, CRC32 `6D536C6E` (moitiés de 1 Mo inversées) | `B6D790A3` |

Tu peux appliquer le patch avec n'importe quel outil IPS (Lunar IPS, Floating IPS…), ou le regénérer avec le script :

```
python build_patch.py chemin/vers/236-p1.p1 sortie/
```

Le script vérifie le CRC, reconnaît le format, puis écrit la ROM patchée et le fichier IPS correspondant.
Les vitesses se règlent en tête de `build_patch.py` : `START_SPEED`, `MAX_SPEED`, `ACCEL_SHIFT`, `PRECISE_SPEED`, `FAST_SPEED`.

### Dans MAME

Par défaut, le pilote `irrmaze` branche un trackball. Il faut lui demander un stick :

```
mame irrmaze -edge joy
```

MAME affichera « WRONG CHECKSUMS » puisque la ROM est modifiée. C'est normal, le jeu tourne.

### Sur une vraie cartouche

À graver : le format MAME (`236-p1.p1` patché), qui correspond au contenu de la puce d'origine. Il faut une EPROM 16 Mbit (27C160 ou équivalent, éventuellement avec un adaptateur). Vérifie si ton programmateur attend l'ordre des octets inversé.

---

## Le cheminement : comment le patch a été trouvé

Ce patch a été mis au point en une session, en travaillant avec Claude (Claude Code). Voici les étapes, fausses pistes comprises : elles expliquent pourquoi le patch final a cette forme.

### 1. Lire le code du jeu

Le romset contient le programme 68000 (`236-p1`), mais aussi un **BIOS spécial** (`236-bios.sp1`) qui n'existe que pour ce jeu. C'était un premier indice que le trackball sortait de l'ordinaire.

Les ROM programme Neo Geo sont stockées en mots de 16 bits inversés : la signature `NEO-GEO` se lit `EN-OEG.O` dans un éditeur hexa. Après remise à l'endroit, le désassembleur fourni avec MAME (`unidasm -arch m68000`) produit un listing lisible de la première moitié de la ROM (la partie toujours visible en `$000000-$0FFFFF`).

### 2. Chercher les accès au matériel

Sur Neo Geo, la manette J1 se lit en `$300000` et la J2 en `$340000`. Le registre `$380001` pilote des sorties, dont un multiplexeur sur le port manette. Un trackball 2 axes doit forcément passer par ce multiplexeur, d'où les recherches de ces adresses dans le code. Elles ont donné :

- deux petites routines en `$0006E2` et `$000702`, qui écrivent sur `$380001` puis lisent `$300000`. Ce sont des lectures de l'axe X et de l'axe Y du trackball, sous forme de compteurs 8 bits ;
- une routine en `$0006D0`, qui calcule un delta (compteur actuel − compteur précédent) ;
- des routines qui transforment ces deltas en faux bits de direction joystick, pour les menus.

### 3. Première version, puis fausse piste

Le premier patch remplaçait ces deux routines par une routine qui lit le stick et fait avancer un compteur virtuel selon la direction tenue. L'idée : faire croire au jeu que le trackball tourne. Le code assemblé était correct, et MAME confirmait que la ROM patchée était bien chargée.

**Mais en jeu, rien ne bougeait.** En relevant la RAM image par image avec un script Lua dans MAME, les compteurs du trackball (`$10FE02…`) restaient égaux aux bits bruts du stick, comme si ma routine n'était jamais appelée.

### 4. La découverte : c'est le BIOS qui lit le trackball

Un *write tap* Lua sur `$10FE00-$10FE1F` (une sonde qui note l'adresse du code qui écrit dans cette zone) a donné la réponse : les écritures venaient de `$C1B318`, donc du **BIOS**, et pas du jeu.

Le même test avec l'Unibios a montré la même chose. Le BIOS gère lui-même ce type de manette. Les routines trouvées dans le jeu à l'étape 2 sont du code mort : jamais appelées en pratique.

### 5. Où le jeu utilise vraiment le trackball

On cherche alors qui **lit** les deltas calculés par le BIOS (`$10FE04` pour X, `$10FE0A` pour Y). Il n'y a qu'un seul endroit, en `$01844E` :

```
01844e: tst.b   ($1,A5)          ; drapeau de debug ?
018452: bne     $184f8           ; -> chemin "joystick"
018456: move.b  $10fe04.l, D0    ; delta X du trackball
...                              ; -> dx en $10A7CE, dy en $10A7D0
```

Le chemin en `$0184F8` est **un mode joystick laissé par les développeurs**, probablement pour tester le jeu sans trackball.
Il lit le stick via les variables du BIOS, convertit la direction en dx/dy de ±1 avec une petite table, puis multiplie la vitesse par 2, 4 ou 8 avec les boutons C/D. Il gère aussi les boutons A/B, au même format que le chemin trackball.

### 6. Le patch final

Plutôt que de simuler un trackball, on force ce chemin joystick et on remplace son contenu :

1. **`$018452`** : `bne` → `bra`. Le jeu prend toujours le chemin joystick.
2. **`$0184F8`** : saut vers une nouvelle routine, logée dans une zone libre de la ROM (`$0F8000`, remplie de `$FF`). Elle :
   - lit **directement** les ports `$300000` et `$340000` (J1 et J2 combinés) ;
   - calcule la vitesse avec **accélération**, en 1/16 de pixel par image, avec une fraction de pixel conservée d'une image à l'autre ;
   - gère les modes précision (C) et rapide (D) ;
   - écrit dx/dy et l'état des boutons au même format que l'original : `-1` à l'appui, puis `1` tant que le bouton est maintenu.
3. **`$018734`** : la routine a besoin de 3 octets de RAM, pris parmi ceux que le jeu remet à zéro mais ne relit jamais (`$10A7D6`, `$10A7D7`, `$10A7DC`). À l'origine, le jeu y copiait l'état des ports au démarrage. Le patch les met à zéro à la place.

### 7. Deuxième piège : le BIOS spécial

Avec l'Unibios, tout marchait du premier coup. Avec le BIOS spécial du jeu, la tige restait immobile.
Ce BIOS ne remplit pas les variables joystick standard (`$10FD96`…) à partir du stick : il les déduit des mouvements du trackball.
D'où le choix de **lire les ports en direct** dans la routine finale. Elle ne dépend plus du BIOS, et le patch marche à l'identique sur les deux.

### 8. Les formats de romset

Le `236-p1` du romset de départ ne correspondait pas au CRC attendu par MAME. Ses deux moitiés de 1 Mo étaient inversées par rapport au dump de référence.
Le script reconnaît donc les deux formats, et le dépôt fournit un IPS pour chacun.

### 9. Vérifications

Tout a été testé dans **MAME 0.287** avec `-edge joy`, en automatisant les manettes par script Lua (voir [`tests/test_mame.lua`](tests/test_mame.lua)), avec le BIOS spécial `asia-sp1` puis l'Unibios 3.3 :

- démarrage, crédit, sélection du personnage, premier niveau ;
- dx/dy relevés en RAM : accélération de 1 à 3 px/frame, les 4 directions dans le bon sens, mode précision, mode rapide, stick J2 ;
- boutons A/B : `-1` à l'appui puis `1` maintenu, identique au trackball ;
- à l'image, la tige se déplace dans le labyrinthe et l'écran défile.

Chaque IPS a aussi été appliqué sur la ROM d'origine, pour confirmer qu'il redonne exactement la ROM patchée.

## Limites connues

- Seul le début du jeu a été testé. Une partie complète reste à faire.
- Rien n'a été testé sur matériel réel.
- Avec le BIOS spécial `236-bios`, les **menus** (gérés par le BIOS) peuvent réagir moins bien au stick qu'avec un BIOS standard. La partie elle-même n'est pas concernée.
- Le jeu d'origine prévoit un souffleur d'air sur la borne, déclenché quand on touche un mur. Le patch ne le concerne pas.

## Contenu du dépôt

```
build_patch.py      génère la ROM patchée et l'IPS (mini-assembleur 68000 intégré)
patches/            les deux patchs IPS prêts à l'emploi
tests/test_mame.lua script de test automatique pour MAME
```

*The Irritating Maze* est une marque et une œuvre de SNK. Ce projet n'y est pas affilié.
