#!/usr/bin/env python3
#
# SPDX-License-Identifier: MIT

import glob
import os
import pathlib
import re
import shutil
import subprocess
import sys

import click


def requireCommands(commands):
    missing = []
    for cmd in commands:
        if shutil.which(cmd) is None:
            missing.append(cmd)

    if len(missing) > 0:
        click.echo(
            "Required commands not found: {}".format(" ".join(missing)), err=True
        )
        sys.exit(1)


def runCommand(cmd):
    p = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
    )
    if p.returncode != 0:
        click.echo(p.stdout, err=True)
        sys.exit(1)

    return p


def getSoftwareLists():
    sls = []
    for p in glob.glob(os.path.join("hash", "*.xml")):
        sls.append(pathlib.Path(p).stem)

    return sorted(sls)


def getOutputName(filename):
    base_name = pathlib.Path(filename).stem.lower()
    output_name = re.sub(r"\W+", "_", base_name, flags=re.ASCII)
    if output_name.endswith("_"):
        output_name = output_name[0:-1]

    return output_name


def getRomPath(sl, name):
    rom_path = os.path.join("roms", sl, name)
    if not os.path.exists(rom_path):
        os.makedirs(rom_path)
    return rom_path


def getCrc32(filename):
    requireCommands(["crc32"])
    p = runCommand(["crc32", filename])
    return p.stdout.strip()


def getSha1(filename):
    requireCommands(["chdman", "sha1sum"])
    if pathlib.Path(filename).suffix.lower() == ".chd":
        cmd = ["chdman", "info", "-i", filename]
        p = runCommand(cmd)
        for line in p.stdout.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":")
            if key == "SHA1":
                sha1 = value.strip()
                break
    else:
        p = runCommand(["sha1sum", filename])
        sha1 = p.stdout.split(" ")[0].strip()

    return sha1


def getSize(filename):
    return pathlib.Path(filename).stat().st_size


def importcd(sl, name, filename):
    requireCommands(["chdman"])
    rom_path = getRomPath(sl, name)
    output_name = getOutputName(filename)
    output = f"{output_name}.chd"

    cmd = ["chdman", "createcd", "-i", filename, "-o", os.path.join(rom_path, output)]
    runCommand(cmd)

    sha1 = getSha1(os.path.join(rom_path, output))

    return (output_name, sha1)


def importhdd(sl, name, filename):
    requireCommands(["chdman"])
    rom_path = getRomPath(sl, name)
    output_name = getOutputName(filename)
    output = f"{output_name}.chd"

    cmd = [
        "chdman",
        "copy",
        "-c",
        "lzma,zlib,huff,flac",
        "-i",
        filename,
        "-o",
        os.path.join(rom_path, output),
    ]
    runCommand(cmd)

    sha1 = getSha1(os.path.join(rom_path, output))

    return (output_name, sha1)


def importflop(sl, name, filename):
    rom_path = getRomPath(sl, name)
    base_name = pathlib.Path(filename).name
    shutil.copy2(filename, rom_path)

    crc32 = getCrc32(filename)
    sha1 = getSha1(filename)
    size = getSize(filename)

    return (base_name, sha1, crc32, size)


def importpart(sl, name, filename, count=0):
    suffix = pathlib.Path(filename).suffix.lower()
    if suffix == ".chd":
        (output_name, sha1) = importhdd(sl, name, filename)
        partname = "hdd"
        if count > 0:
            partname = f"{partname}{count}"
        if sl == "ibm5150_hdd":
            interface = "st_hdd"
        elif sl == "ibm5170_hdd":
            interface = "ide_hdd"
        else:
            interface = "scsi_hdd"
        dataarea = f"""\t\t\t<diskarea name="harddriv">\n\t\t\t\t<disk name="{output_name}" sha1="{sha1}" writeable="yes" />\n\t\t\t</diskarea>"""
    elif suffix == ".iso":
        (output_name, sha1) = importcd(sl, name, filename)
        partname = "cdrom"
        if count > 0:
            partname = f"{partname}{count}"
        interface = "cdrom"
        dataarea = f"""\t\t\t<diskarea name="cdrom">\n\t\t\t\t<disk name="{output_name}" sha1="{sha1}" />\n\t\t\t</diskarea>"""
    else:
        (output_name, sha1, crc32, size) = importflop(sl, name, filename)
        partname = "flop"
        if count > 0:
            partname = f"{partname}{count}"
        if size == 368640 or size == 1228800:
            interface = "floppy_5_25"
        elif size == 737280 or size == 1474560:
            interface = "floppy_3_5"
        else:
            interface = "TODO"
        dataarea = f"""\t\t\t<dataarea name="flop" size="{size}">\n\t\t\t\t<rom name="{output_name}" size="{size}" crc="{crc32}" sha1="{sha1}"/>\n\t\t\t</dataarea>"""

    partxml = f"""\t\t<part name="{partname}" interface="{interface}">\n{dataarea}\n\t\t</part>"""

    return partxml


def importparts(sl, name, filenames):
    parts = []
    if len(filenames) == 1:
        count = 0
    else:
        count = 1
    for filename in filenames:
        parts.append(importpart(sl, name, filename, count))
        count += 1

    xml = f"""\t<software name="{name}">\n\t\t<description>TODO</description>\n\t\t<year>TODO</year>\n\t\t<publisher>TODO</publisher>\n"""
    for part in parts:
        xml += f"{part}\n"
    xml += """\t</software>"""

    return xml


@click.group()
def cli():
    """A simple CLI to inspect and manage MAME software list definitions"""
    pass


@cli.command()
def list():
    for l in getSoftwareLists():
        click.echo(l)


@cli.command()
@click.argument("sl")
@click.argument("name")
@click.argument("filename", type=click.Path(exists=True, dir_okay=False), nargs=-1)
def importp(sl, name, filename):
    if len(name) > 16:
        click.echo(f"{name} must be 16 chars or less", err=True)
        sys.exit(1)

    xml = importparts(sl, name, filename)
    click.echo(xml)


if __name__ == "__main__":
    cli()
