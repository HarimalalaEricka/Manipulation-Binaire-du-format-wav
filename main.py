import math
# import pygame

def open_file_extract_data(file):
    with open(file, "rb") as f:
        contenu = f.read()
    return bytearray(contenu)

def rewrite_audio_file(output_file, header, audio_data):
    with open(output_file, "wb") as f:
        f.write(header + audio_data)
    print("Fichier créé :", output_file)
    return output_file

def little_endian(audio_data, nbr_bits):
    """Décode les bytes en samples signés, quel que soit le nombre de bits."""
    bytes_per_sample = nbr_bits // 8
    max_val = 2 ** (nbr_bits - 1)
    full_range = 2 ** nbr_bits
    samples = []

    for i in range(0, len(audio_data) - (bytes_per_sample - 1), bytes_per_sample):
        valeur = int.from_bytes(audio_data[i:i + bytes_per_sample], byteorder='little', signed=False)
        if valeur >= max_val:
            valeur -= full_range
        samples.append(valeur)

    return samples

def little_endian_inverse(samples, nbr_bits):
    """Encode les samples signés en bytes little-endian."""
    bytes_per_sample = nbr_bits // 8
    full_range = 2 ** nbr_bits
    audio_out = bytearray()

    for s in samples:
        if s < 0:
            s += full_range
        audio_out += s.to_bytes(bytes_per_sample, byteorder='little')

    return audio_out

def lecture_en_tete(file):
    print("LECTURE DES EN-TETE DU FICHIER")
    data = open_file_extract_data(file)
    header = data[:44]
    freq_echan = int.from_bytes(header[24:28], byteorder='little')
    canaux     = int.from_bytes(header[22:24], byteorder='little')
    quant      = int.from_bytes(header[34:36], byteorder='little')
    print("  Fréquence d'échantillonnage :", freq_echan, "Hz")
    print("  Nombre de canaux            :", canaux)
    print("  Bits par échantillon        :", quant)
    return freq_echan, canaux, quant

def find_offset_audio_data(file):
    data = open_file_extract_data(file)
    offset = 0
    for i in range(len(data) - 4):
        if data[i:i+4] == b"data":
            offset = i + 8  # skip "data" (4) + taille chunk (4)
            break
    print("Data offset:", offset)
    return data[:offset], data[offset:]

def update_header(header, sample_rate, canaux, quant, data_size):
    """Met à jour tous les champs du header WAV dépendants du format."""
    bytes_per_sample = quant // 8

    header[24:28] = sample_rate.to_bytes(4, "little")
    header[28:32] = (sample_rate * canaux * bytes_per_sample).to_bytes(4, "little")
    header[32:34] = (canaux * bytes_per_sample).to_bytes(2, "little")
    header[34:36] = quant.to_bytes(2, "little")

    data_size_offset = header.find(b'data') + 4
    header[data_size_offset:data_size_offset + 4] = data_size.to_bytes(4, "little")
    header[4:8] = (len(header) - 8 + data_size).to_bytes(4, "little")

    return header

def changer_echantillonnage(file):
    print("\nCHANGEMENT DE LA FREQUENCE D'ECHANTILLONNAGE")
    header, audio_data = find_offset_audio_data(file)

    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")

    samples = little_endian(audio_data, quant)

    new_samples = [(samples[i] + samples[i+1]) // 2 for i in range(0, len(samples) - 1, 2)]

    audio_out = little_endian_inverse(new_samples, quant)
    header = update_header(header, sample_rate // 2, canaux, quant, len(audio_out))

    return rewrite_audio_file("nouveau_echantillonnage.wav", header, audio_out)

def changer_quantification(file, new_quant):
    print(f"\nCHANGEMENT DE QUANTIFICATION -> {new_quant} bits")
    header, audio_data = find_offset_audio_data(file)

    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")

    samples = little_endian(audio_data, quant)

    shift = quant - new_quant
    if shift > 0:
        new_samples = [s >> shift for s in samples]
    else:
        new_samples = [s << (-shift) for s in samples]

    audio_out = little_endian_inverse(new_samples, new_quant)
    header = update_header(header, sample_rate, canaux, new_quant, len(audio_out))

    return rewrite_audio_file("nouveau_quantification.wav", header, audio_out)

def desaturation(file, gain=3.0):
    # gain > 1 → amplifie → les valeurs de sortie dépassent les valeurs d'entrée
    # gain = 1 → tanh seul → très légère compression
    # 0 < gain < 1 → atténue → les valeurs de sortie sont inférieures aux valeurs d'entrée
    # gain = 0 → tout devient 0 (silence)
    # gain < 0 → même amplitude, phase inversée
    print("\nDESATURATION")
    header, audio_data = find_offset_audio_data(file)

    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")

    max_val = 2 ** (quant - 1) - 1
    min_val = -(2 ** (quant - 1))

    samples = little_endian(audio_data, quant)

    print("Avant :")
    print(" ", min(samples), max(samples))

    new_samples = []
    for s in samples:
        x = s / max_val                 # normalise [-1.0, 1.0]
        x = math.tanh(x * gain)        # amplifie puis soft clip
        s_out = int(x * max_val)
        s_out = max(min_val, min(max_val, s_out))
        new_samples.append(s_out)

    print("Après :")
    print(" ", min(new_samples), max(new_samples))

    audio_out = little_endian_inverse(new_samples, quant)
    header = update_header(header, sample_rate, canaux, quant, len(audio_out))

    return rewrite_audio_file("nouveau_desature.wav", header, audio_out)

def normalisation(file):
    print("\nNORMALISATION")
    header, audio_data = find_offset_audio_data(file)

    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")

    max_val = 2 ** (quant - 1) - 1
    min_val = -(2 ** (quant - 1))

    samples = little_endian(audio_data, quant)

    print("Avant :")
    print(" ", min(samples), max(samples))

    # Trouver l'amplitude maximale
    max_sample = max(abs(s) for s in samples)

    if max_sample == 0:
        print("Signal vide, rien à normaliser.")
        return

    # Calculer le gain pour atteindre max_val sans dépasser
    gain = max_val / max_sample

    print(f"  Amplitude max trouvée : {max_sample}")
    print(f"  Gain appliqué         : {gain:.4f}")

    # Appliquer le gain + clamp de sécurité
    new_samples = []
    for s in samples:
        s_out = int(s * gain)
        s_out = max(min_val, min(max_val, s_out))
        new_samples.append(s_out)

    print("Après :")
    print(" ", min(new_samples), max(new_samples))

    audio_out = little_endian_inverse(new_samples, quant)
    header = update_header(header, sample_rate, canaux, quant, len(audio_out))

    return rewrite_audio_file("nouveau_normalise.wav", header, audio_out)


def separer_canaux(samples, canaux):
    return [
        samples[i::canaux]
        for i in range(canaux)
    ]

def fusionner_canaux(canaux_list):
    return [
        sample
        for i in range(len(canaux_list[0]))
        for sample in (c[i] for c in canaux_list)
    ]

def create_audio_mono(file, type_canal):
    header, audio_data = find_offset_audio_data(file)
    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")
    samples = little_endian(audio_data, quant)
    channels = separer_canaux(samples, canaux)
    if type_canal == "left":
        audio_out = little_endian_inverse(channels[0], quant)
    elif type_canal == "right":
        audio_out = little_endian_inverse(channels[1], quant)
    else:
        print("Erreur de type de canal")
        return None
    header = update_header(header, sample_rate, 1, quant, len(audio_out))
    return rewrite_audio_file("son_mono.wav", header, audio_out)

def create_audio_stereo_muet(file, canal_muet):
    header, audio_data = find_offset_audio_data(file)
    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")
    samples = little_endian(audio_data, quant)
    channels = separer_canaux(samples, canaux)
    if canal_muet == "left":
        channels[0] = [0] * len(channels[0])
    elif canal_muet == "right":
        if canaux > 1:
            channels[1] = [0] * len(channels[1])
    else:
        print("Erreur type canal")
        return None
    new_samples = fusionner_canaux(channels)
    audio_out = little_endian_inverse(new_samples, quant)
    header = update_header(header, sample_rate, canaux, quant, len(audio_out))
    return rewrite_audio_file("son_stereo_muet.wav", header, audio_out)

def create_audio_stereo_duplic(file, canal):
    header, audio_data = find_offset_audio_data(file)
    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")
    samples = little_endian(audio_data, quant)
    channels = separer_canaux(samples, canaux)
    if canal == "left":
        channels[1] = channels[0]  # droite = gauche
    elif canal == "right":
        channels[0] = channels[1]  # gauche = droite
    else:
        print("Erreur type canal")
        return None
    new_samples = fusionner_canaux(channels)
    audio_out = little_endian_inverse(new_samples, quant)
    header = update_header(header, sample_rate, canaux, quant, len(audio_out))
    return rewrite_audio_file("son_stereo_duplic.wav", header, audio_out)

def low_pass(signal):
    filtered = []
    alpha = 0.1  # plus petit = plus de basses
    prev = 0
    for s in signal:
        prev = prev + alpha * (s - prev)
        filtered.append(int(prev))
    return filtered

# filtrage basses frequence
def stereo_to_21_audio(file):
    header, audio_data = find_offset_audio_data(file)
    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    samples = little_endian(audio_data, quant)
    channels = separer_canaux(samples, 2)
    left = channels[0]
    right = channels[1]
    # 1. création canal LFE (moyenne L/R)
    sub = [(l + r) // 2 for l, r in zip(left, right)]
    sub = low_pass(sub)
    new_samples = fusionner_canaux([left, right, sub])
    audio_out = little_endian_inverse(new_samples, quant)
    header = update_header(header, sample_rate, 3, quant, len(audio_out))
    return rewrite_audio_file("audio_21.wav", header, audio_out)

def up_mixing_51(file, attenuation):
    header, audio_data = find_offset_audio_data(file)
    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    samples = little_endian(audio_data, quant)
    
    # stéréo de base
    channels = separer_canaux(samples, 2)
    left = channels[0]
    right = channels[1]

    # création des canaux
    max_val = 2 ** (quant - 1) - 1
    min_val = -(2 ** (quant - 1))
    central = [max(min_val, min(max_val, l + r)) for l, r in zip(left, right)]
    lfe     = [(l + r) // 2 for l, r in zip(left, right)]
    ls = [max(min_val, min(max_val, int(l * attenuation))) for l in left]
    rs = [max(min_val, min(max_val, int(r * attenuation))) for r in right]

    new_samples = fusionner_canaux([left, right, central, lfe, ls, rs])
    audio_out = little_endian_inverse(new_samples, quant)
    canaux = 6
    header = update_header(header, sample_rate, canaux, quant, len(audio_out))
    return rewrite_audio_file("up_mixing_51.wav", header, audio_out)

def changer_vitesse(file, facteur):
    header, audio_data = find_offset_audio_data(file)

    quant       = int.from_bytes(header[34:36], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    canaux      = int.from_bytes(header[22:24], "little")

    nouveau_sample_rate = int(sample_rate * facteur)
    header = update_header(header, nouveau_sample_rate, canaux, quant, len(audio_data))
    return rewrite_audio_file("nouveau_vitesse.wav", header, audio_data)

def generate_sine(sample_rate, duration=1, freq=440, amplitude=32767):
    samples = []
    total = int(sample_rate * duration)

    for n in range(total):
        t = n / sample_rate
        value = int(amplitude * math.sin(2 * math.pi * freq * t))
        samples.append(value)

    return samples

def generate_5_1(samples_mono):
    total = len(samples_mono)
    output = []
    for i in range(total):
        base = samples_mono[i]
        # position du son dans l’espace (0 → 5)
        pos = (i / total) * 5
        # gains par canal (effet déplacement)
        L   = base * max(0, 1 - abs(pos - 0))
        R   = base * max(0, 1 - abs(pos - 1))
        C   = base * max(0, 1 - abs(pos - 2))
        LFE = base * 0.4
        LS  = base * max(0, 1 - abs(pos - 3))
        RS  = base * max(0, 1 - abs(pos - 4))
        output.extend([
            int(L),
            int(R),
            int(C),
            int(LFE),
            int(LS),
            int(RS)
        ])
    return output

def create_wav_51(filename, samples, sample_rate=44100, quant=16):
    canaux = 6

    audio_bytes = little_endian_inverse(samples, quant)

    header = bytearray(44)

    # RIFF
    header[0:4] = b"RIFF"
    header[8:12] = b"WAVE"

    # fmt
    header[12:16] = b"fmt "
    header[16:20] = (16).to_bytes(4, "little")
    header[20:22] = (1).to_bytes(2, "little")  # PCM

    header[22:24] = canaux.to_bytes(2, "little")
    header[24:28] = sample_rate.to_bytes(4, "little")

    bytes_per_sample = quant // 8
    byte_rate = sample_rate * canaux * bytes_per_sample
    header[28:32] = byte_rate.to_bytes(4, "little")

    block_align = canaux * bytes_per_sample
    header[32:34] = block_align.to_bytes(2, "little")

    header[34:36] = quant.to_bytes(2, "little")

    # data chunk
    header[36:40] = b"data"
    header[40:44] = len(audio_bytes).to_bytes(4, "little")

    # RIFF size
    header[4:8] = (36 + len(audio_bytes)).to_bytes(4, "little")

    return rewrite_audio_file(filename, header, audio_bytes)

# def jouer_audio(file):
    print("\nLECTURE AVEC PYGAME")

    pygame.mixer.init()   # initialise le système audio
    pygame.mixer.music.load(file)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        continue

file = "music-sample-44100hz-16bit.wav"
lecture_en_tete(file)

new_file = changer_echantillonnage(file)
lecture_en_tete(new_file)

new_file2 = changer_quantification(file, 8)
lecture_en_tete(new_file2)

new_file3 = desaturation(file, gain=0.5)
new_file4 = normalisation(file)
new_file5 = create_audio_mono(file, "right")
new_file6 = create_audio_stereo_muet(file, "left")
new_file7 = create_audio_stereo_duplic(file, "left")
new_file8 = stereo_to_21_audio(file)
new_file9 = up_mixing_51(file, attenuation=0.5)
changer_vitesse("up_mixing_51.wav", facteur=3.0)

mono = generate_sine(sample_rate=44100, duration=1, freq=440)
samples_51 = generate_5_1(mono)
create_wav_51("synth_5_1.wav", samples_51)
lecture_en_tete(file)
