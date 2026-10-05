# Vegen Emu

Vegen Emu is een kleine Ubuntu-tool voor een Android-emulator. De app opent een live venster met:

- succesvolle vegen naar links en rechts;
- totaal aantal succesvolle vegen;
- percentage links;
- knoppen voor Start, Stop en Reset.

De swipe-service zoekt naar een user-systemd service met `android-emulator` in de naam. De naam hoeft dus niet exact `android-emulator-b18a86bd2882.service` te zijn.

De teller telt een horizontale veeg alleen als succesvol wanneer ADB de opdracht uitvoert en een tijdelijke schermvergelijking genoeg verandering ziet. Screenshots worden niet opgeslagen.

## Installeren op Ubuntu

```bash
git clone https://github.com/dodriex/vegen-emu.git
cd vegen-emu
./install.sh
```

Als Python/Tkinter/Pillow ontbreken:

```bash
sudo apt install python3-tk python3-pil
```

Open daarna `Vegen Emu` vanaf je bureaublad of start:

```bash
~/.local/bin/vegen-emu
```

## ADB instellen

De tool zoekt `adb` automatisch via `PATH` en bekende Android SDK-locaties. Als jouw `adb` ergens anders staat:

```bash
export VEGEN_EMU_ADB=/pad/naar/platform-tools/adb
```

Standaard gebruikt de tool:

```bash
VEGEN_EMU_ADB_HOST=127.0.0.1
VEGEN_EMU_ADB_PORT=5038
VEGEN_EMU_ADB_SERIAL=emulator-5554
```

Je kunt die waarden aanpassen als je emulator anders bereikbaar is.

## Gedrag

Per cyclus:

1. Na een succesvolle links/rechts-veeg wacht de service 0.5 tot 0.75 seconden.
2. Hij scrollt eerst omhoog om niet onderaan te blijven hangen.
3. Hij scrollt omlaag totdat de bodemdetectie geen beweging meer ziet, of totdat de korte bovengrens is bereikt.
4. Hij veegt links met ongeveer 5-6% kans, anders rechts.

Runtimebestanden staan in `~/.local/share/vegen-emu/outputs`.
