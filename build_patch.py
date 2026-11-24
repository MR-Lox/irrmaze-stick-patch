"""Irritating Maze (irrmaze, Neo Geo) - patch "stick arcade" au lieu du trackball.

Fonctionnement du jeu d'origine
  Le BIOS lit le trackball et range les deplacements X/Y en $10FE04/$10FE0A.
  En $01844E, le jeu les copie dans ses variables de deplacement
  ($10A7CE dx, $10A7D0 dy) et lit les boutons en $10FE10/$10FE11.
  Juste a cote ($0184F8) existe un chemin "joystick" cache (mode debug,
  active par le drapeau $108001) qui lit le stick via les variables standard
  du BIOS ($10FD96...).

Le patch
  1. force toujours le chemin joystick (bne -> bra en $018452) ;
  2. remplace ce chemin par une routine (en zone libre $0F8000) qui :
     - lit les sticks J1 et J2 directement sur les ports $300000/$340000
       (n'importe lequel des deux pilote ; marche avec tous les BIOS) ;
     - deplace de 1 px/frame des l'appui, puis accelere jusqu'a 3 px/frame ;
     - C maintenu : mode precision ; D maintenu : mode rapide ;
     - A / B = boutons 1 / 2 du jeu (memes valeurs que le trackball) ;
  3. utilise 3 octets de RAM que le jeu ne lit jamais : $10A7D6 (vitesse),
     $10A7D7 (fraction de pixel), $10A7DC (boutons de la frame precedente).

Usage : python build_patch.py <236-p1 d'origine> <dossier de sortie>
Produit : le 236-p1 patche (meme format que l'original) + un patch IPS.
"""
import hashlib
import struct
import sys
import zlib
from pathlib import Path

# Vitesses en 1/16 de pixel par frame
START_SPEED = 16    # 1 px/frame des l'appui
MAX_SPEED = 48      # 3 px/frame
ACCEL_SHIFT = 1     # +1/16 px toutes les 2^ACCEL_SHIFT frames (16->48 en ~1 s)
PRECISE_SPEED = 6   # bouton C : ~0,4 px/frame
FAST_SPEED = 64     # bouton D : 4 px/frame

FREE = 0x0F8000     # zone de padding ($FF) inutilisee de la ROM programme

ORIG_CRC = 0x4C2FF660   # 236-p1.p1 du set MAME actuel
OLD_CRC = 0x6D536C6E    # 236-p1.bin des anciens sets (moities inversees)

# Variables (relatives a A5 = $108000)
PREV = 0x27DC                   # octet seulement remis a zero par le jeu, jamais lu
BTN_ANY, BTN1, BTN2 = 0x27C4, 0x27C6, 0x27C8
DX, DY = 0x27CE, 0x27D0
SPEED, FRAC = 0x27D6, 0x27D7    # octets liberes (vitesse en 1/16 px, fraction)


def w(*words):
    return b"".join(struct.pack(">H", x & 0xFFFF) for x in words)


def l(x):
    return struct.pack(">I", x)


class Asm:
    """Mini-assembleur : octets bruts + branches courtes (.s) vers des labels."""

    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fix = []

    def __call__(self, data):
        self.code += data

    def label(self, name):
        self.labels[name] = len(self.code)

    def bra(self, opcode, name):  # 0x60 bra, 0x66 bne, 0x67 beq, 0x64 bcc
        self.fix.append((len(self.code), opcode, name))
        self.code += b"\0\0"

    def build(self):
        for pos, op, name in self.fix:
            disp = self.labels[name] - (pos + 2)
            assert -128 <= disp <= 127 and disp != 0, (name, disp)
            self.code[pos] = op
            self.code[pos + 1] = disp & 0xFF
        return bytes(self.code)


def stick_code():
    """Remplace le chemin joystick du jeu. Entree : A5 = $108000.
    Ecrit dx/dy et les boutons comme le fait le chemin trackball."""
    a = Asm()
    # D0 = stick courant (J1 | J2, lu directement sur les ports : marche avec
    # tous les BIOS, y compris le BIOS special 236 qui ne remplit pas P1CURRENT)
    # D3 = boutons nouvellement appuyes
    a(w(0x1039) + l(0x300000))     # move.b $300000.l,D0   (J1, actif bas)
    a(w(0xC039) + l(0x340000))     # and.b  $340000.l,D0   (J2, actif bas)
    a(w(0x4600))                   # not.b  D0
    a(w(0x162D, PREV))             # move.b PREV(A5),D3
    a(w(0x4603))                   # not.b  D3
    a(w(0xC600))                   # and.b  D0,D3
    a(w(0x1B40, PREV))             # move.b D0,PREV(A5)
    # Boutons : 1 = maintenu, -1 = vient d'etre appuye (comme l'original)
    a(w(0x7200, 0x7400))           # moveq #0,D1 ; moveq #0,D2
    a(w(0x0800, 0x0004)); a.bra(0x67, "nb1")   # btst #4,D0 (A)
    a(w(0x7201))                                # moveq #1,D1
    a(w(0x0803, 0x0004)); a.bra(0x67, "nb1")   # btst #4,D3
    a(w(0x4441))                                # neg.w D1
    a.label("nb1")
    a(w(0x0800, 0x0005)); a.bra(0x67, "nb2")   # btst #5,D0 (B)
    a(w(0x7401))                                # moveq #1,D2
    a(w(0x0803, 0x0005)); a.bra(0x67, "nb2")   # btst #5,D3
    a(w(0x4442))                                # neg.w D2
    a.label("nb2")
    a(w(0x3B41, BTN1))             # move.w D1,BTN1(A5)
    a(w(0x3B42, BTN2))             # move.w D2,BTN2(A5)
    a(w(0x8441))                   # or.w D1,D2
    a(w(0x3B42, BTN_ANY))          # move.w D2,BTN_ANY(A5)
    # Vitesse
    a(w(0x7600))                   # moveq #0,D3
    a(w(0x1200))                   # move.b D0,D1
    a(w(0x0201, 0x000F))           # andi.b #$0F,D1
    a.bra(0x67, "nodir")           # beq.s nodir
    a(w(0x0800, 0x0006)); a.bra(0x67, "notc")  # btst #6,D0 (C)
    a(w(0x7600 | PRECISE_SPEED)); a.bra(0x60, "frac")
    a.label("notc")
    a(w(0x0800, 0x0007)); a.bra(0x67, "notd")  # btst #7,D0 (D)
    a(w(0x7600 | FAST_SPEED)); a.bra(0x60, "frac")
    a.label("notd")
    # SPEED contient la vitesse << ACCEL_SHIFT (acceleration plus douce)
    a(w(0x362D, SPEED))            # move.w SPEED(A5),D3   (octet fort = vitesse*2^s, faible = fraction)
    a(w(0xE04B))                   # lsr.w #8,D3
    a(w(0x0C03, START_SPEED << ACCEL_SHIFT)); a.bra(0x64, "ge")  # cmpi.b
    a(w(0x7600 | (START_SPEED << ACCEL_SHIFT)))                  # moveq
    a.label("ge")
    a(w(0x0C03, MAX_SPEED << ACCEL_SHIFT)); a.bra(0x64, "st")    # cmpi.b
    a(w(0x5203))                   # addq.b #1,D3
    a.label("st")
    a(w(0x1B43, SPEED))            # move.b D3,SPEED(A5)
    a(w(0xE00B | (ACCEL_SHIFT << 9)))  # lsr.b #ACCEL_SHIFT,D3 (1..7)
    a.label("frac")
    a(w(0xD62D, FRAC))             # add.b FRAC(A5),D3
    a(w(0x1203))                   # move.b D3,D1
    a(w(0x0201, 0x000F))           # andi.b #$0F,D1
    a(w(0x1B41, FRAC))             # move.b D1,FRAC(A5)
    a(w(0xE80B))                   # lsr.b #4,D3   -> pixels de cette frame
    # Directions : bit0 haut, bit1 bas, bit2 gauche, bit3 droite
    a(w(0x7200, 0x7400))           # moveq #0,D1 ; moveq #0,D2
    a(w(0x0800, 0x0003)); a.bra(0x67, "d1"); a(w(0xD243))  # btst #3 ; add.w D3,D1
    a.label("d1")
    a(w(0x0800, 0x0002)); a.bra(0x67, "d2"); a(w(0x9243))  # btst #2 ; sub.w D3,D1
    a.label("d2")
    a(w(0x0800, 0x0001)); a.bra(0x67, "d3"); a(w(0xD443))  # btst #1 ; add.w D3,D2
    a.label("d3")
    a(w(0x0800, 0x0000)); a.bra(0x67, "out"); a(w(0x9443))  # btst #0 ; sub.w D3,D2
    a.label("out")
    a(w(0x3B41, DX))               # move.w D1,DX(A5)
    a(w(0x3B42, DY))               # move.w D2,DY(A5)
    a(w(0x4E75))                   # rts
    a.label("nodir")
    a(w(0x426D, SPEED))            # clr.w SPEED(A5)  (vitesse + fraction)
    a(w(0x7200, 0x7400))           # moveq #0,D1 ; moveq #0,D2
    a.bra(0x60, "out")
    return a.build()


def patches():
    code = stick_code()
    return [
        # tst.b ($1,A5) / bne $184F8 -> bra $184F8 : toujours le chemin joystick
        (0x018452, w(0x6000, 0x00A4), w(0x6600, 0x00A4)),
        # chemin joystick : jsr nouvelle routine ; bra.w $18566 (bsr $181AA ; rts)
        (0x0184F8, w(0x4EB9) + l(FREE) + w(0x6000, 0x18566 - 0x184FE - 2),
         w(0x102D, 0x7D96, 0x3600, 0x0240, 0x000F)),
        # init : SPEED/FRAC etaient remplis avec les ports d'entree -> mis a 0
        (0x018734, w(0x3B40, SPEED, 0x4E71, 0x4E71, 0x4E71, 0x4E71, 0x4E71, 0x4E71),
         w(0x1B79, 0x0030, 0x0000, 0x27D6, 0x1B79, 0x0034, 0x0000, 0x27D7)),
        (FREE, code, b"\xFF" * len(code)),
    ]


def swap16(b):
    b = bytearray(b)
    b[0::2], b[1::2] = b[1::2], b[0::2]
    return bytes(b)


def make_ips(orig, new):
    out = bytearray(b"PATCH")
    i = 0
    while i < len(new):
        if new[i] == orig[i]:
            i += 1
            continue
        j = i
        while j < len(new) and new[j] != orig[j] and j - i < 0xFFFF:
            j += 1
        assert i != 0x454F46  # "EOF"
        out += i.to_bytes(3, "big") + (j - i).to_bytes(2, "big") + new[i:j]
        i = j
    out += b"EOF"
    return bytes(out)


def main():
    src, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    orig = src.read_bytes()
    crc = zlib.crc32(orig)
    # Format MAME actuel : moitie "banque" d'abord, programme ensuite.
    # Ancien format : les deux moities de 1 Mo sont inversees.
    if crc == ORIG_CRC:
        halves = True
    elif crc == OLD_CRC:
        halves = False
    else:
        sys.exit(f"CRC inattendu {crc:08X} (attendu {ORIG_CRC:08X} ou {OLD_CRC:08X})")
    prog = orig[0x100000:] + orig[:0x100000] if halves else orig
    be = bytearray(swap16(prog))  # le fichier est en mots inverses (little endian)
    for addr, data, expect in patches():
        assert len(data) == len(expect) or expect.startswith(b"\xFF"), hex(addr)
        assert be[addr:addr + len(expect)] == expect, f"octets inattendus en {addr:06X}"
        be[addr:addr + len(data)] = data
    new = swap16(bytes(be))
    if halves:
        new = new[0x100000:] + new[:0x100000]
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / src.name).write_bytes(new)
    ips = "irrmaze_stick.ips" if halves else "irrmaze_stick_ancien_format.ips"
    (outdir / ips).write_bytes(make_ips(orig, new))
    print(f"{src.name} patche : CRC32 {zlib.crc32(new):08X} SHA1 {hashlib.sha1(new).hexdigest()}")
    print(f"IPS : {outdir / ips}")


if __name__ == "__main__":
    main()
