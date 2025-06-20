#!/usr/bin/env python3

import argparse
import pathlib
import tomllib
import typing

from termcolor import cprint

#TODO: fail gracefully if paths not present

# provide your dsda_doom_data folder or equivalent here
ROOT_PATH = pathlib.Path("").expanduser()

# provide a TOML file here with max exceptions
EXCEPTIONS_FILE = pathlib.Path("").expanduser()

REQUIRE_ITEMS = False

UNPLAY_COLOR = "red"
UNMAX_COLOR = "light_yellow"
MAX_COLOR = "light_green"
TOTALS_COLOR = "light_blue"

PRINT_MAX_WADS = True
PRINT_MAX_LVLS = False #quirk: only if PRINT_ONCE_PER_WAD is unset
PRINT_UNMAX_LVLS = True
PRINT_UNPLAY_LVLS = True
PRINT_ONCE_PER_WAD: bool

TOTAL_MAXED_LVLS: int
TOTAL_DEAD_DEMONS: int

PWAD_INDENT_STRING = "    "

class Exceptions_Table(typing.NamedTuple):
    WAD_EXCEPTIONS: list
    KILL_EXCEPTIONS: list
    SECRET_EXCEPTIONS: list
    ITEM_EXCEPTIONS: list
    PLAY_EXCEPTIONS: list

#TODO: lift ALL printing behavior into its own distinct step
# this will also make paginating output easier


# currently only stats.txt version 1 is supported, described below
# dsda-doom 0.28.1 and cherry-doom 2.0.0 both produce this version
# old versions of cherry doom produce a version 2, the spec is identical
# except for two extra ints at the end, best attempts and total attempts, in that order
#TODO: nyan doom?
# relevant source lives in prboom2/src/dsda/wad_stats.c

# stats.txt format spec: 1 line of just current version, 1 line of just total kills,
# then per line: lump (length 8 str), ep, map, best skill, best time, best max time, best sk5 time,
# total exits, total kills, best kills, best items, best secrets,
# max kills, max items, max secrets
# all fields are ints except lump, -1 indicates no data
#TODO: support negative numbers to indicate count of inaccessible kills/items/secrets
# (for example, secrets exception of "-2" indicates that 2 secrets are inaccessible,
# so therefore the required secrets should be max secrets - 2)
class DSDA_Stat_Line(typing.NamedTuple):
    iwad: str
    pwad: str
    lump_name: str
    ep_num: int
    map_num: int
    best_skill: int
    best_time: int
    best_max_time: int
    best_nm_time: int
    total_wins: int
    total_kills: int
    best_kills: int
    best_items: int
    best_secrets: int
    max_kills: int
    max_items: int
    max_secrets: int

    @property
    def maxed(self) -> bool:
        kill_max = self.best_kills == self.max_kills
        secret_max = self.best_secrets == self.max_secrets
        return kill_max and secret_max

    @property
    def item_maxed(self):
        return self.best_items == self.max_items

    @property
    def triplet_id(self):
        return [self.iwad, self.pwad, self.lump_name]

    def max_exception(self, exc_table):
        is_exception = False
        for level in exc_table.KILL_EXCEPTIONS:
            if self.triplet_id != level[:3]:
                continue
            if self.best_kills >= level[3]:
                is_exception = True
        for level in exc_table.SECRET_EXCEPTIONS:
            if self.triplet_id != level[:3]:
                continue
            if self.best_secrets >= level[3]:
                is_exception = True
            else: #level should match BOTH exception criteria if present
                is_exception = False
        return is_exception

    def item_exception(self, exc_table):
        is_exception = False
        for level in exc_table.ITEM_EXCEPTIONS:
            if self.triplet_id != level[:3]:
                continue
            if self.best_items >= level[3]:
                is_exception = True
        return is_exception


def format_pwad(iwad, pwad):
    if pwad:
        return f"{pwad.upper()} (iwad {iwad.upper()})"
    return iwad.upper()

def format_num_maps(num_maps):
    if num_maps == 1:
        s = ""
    else:
        s = "s"
    return f"({num_maps} map{s})"

def check_max(iwad, pwad, stat_line_raw, exc_table): #return whether the level is considered "maxed"
    global TOTAL_MAXED_LVLS, TOTAL_DEAD_DEMONS
    level = DSDA_Stat_Line(iwad, pwad, *stat_line_raw)
    TOTAL_DEAD_DEMONS += level.best_kills #TODO: consider total_kills instead? both?
    if level.best_time == -1: #level not finished
        if level.triplet_id in exc_table.PLAY_EXCEPTIONS:
            return True
        if PRINT_UNPLAY_LVLS:
            print(PWAD_INDENT_STRING if pwad else "", end="")
            cprint(f"Level {level.lump_name} in {format_pwad(iwad, pwad)} isn't beaten!", UNPLAY_COLOR)
            return False
    #TODO: reorganize these into a single if statement, prefer notifying missed kills to missed items
    if REQUIRE_ITEMS and not level.item_maxed:
        if not level.item_exception(exc_table):
            if PRINT_UNMAX_LVLS:
                print(PWAD_INDENT_STRING if pwad else "", end="")
                cprint(f"Level {level.lump_name} in {format_pwad(iwad, pwad)} is missing items!", UNMAX_COLOR)
            return False
    if not level.maxed:
        if not level.max_exception(exc_table):
            if PRINT_UNMAX_LVLS:
                print(PWAD_INDENT_STRING if pwad else "", end="")
                cprint(f"Level {level.lump_name} in {format_pwad(iwad, pwad)} isn't maxed!", UNMAX_COLOR)
                return False
    TOTAL_MAXED_LVLS += 1
    if PRINT_MAX_LVLS and not PRINT_ONCE_PER_WAD: #TODO: prints even if the entire wad is maxed
        print(PWAD_INDENT_STRING if pwad else "", end="")
        cprint(f"Level {level.lump_name} in {format_pwad(iwad, pwad)} is maxed!", MAX_COLOR)
    return True

def parse_stats(path, iwad, pwad, exc_table):
    # Refer to stats.txt format spec above, near the definition of DSDA_Stat_Line
    with open(path, 'r', encoding="utf-8") as stat_file:
        stats_ver = stat_file.readline()
        _ = stat_file.readline()
        stat_list = stat_file.readlines()
    #stats files should never be very long, so it's fine to just dump them into RAM like that
    if stats_ver.strip() != "1":
        raise RuntimeError(f"Unsupported stats.txt version {stats_ver.strip()} found in {format_pwad(iwad, pwad)}")
    wad_max = True
    for line in stat_list: #todo: check skill?
        stats = line.split()
        stats[1:] = [int(stat) for stat in stats[1:]] #convert all but the first value into ints
        assert len(stats) == 15
        if not check_max(iwad, pwad, stats, exc_table):
            wad_max = False
            if PRINT_ONCE_PER_WAD:
                break #TODO: Bug! Max levels that come *after* the earliest unmax level won't be counted
    if wad_max and PRINT_MAX_WADS:
        num_maps = len(stat_list)
        print(PWAD_INDENT_STRING if pwad else "", end="")
        cprint(f"*** Well done! {format_pwad(iwad, pwad)} is completely maxed! {format_num_maps(num_maps)} ***", MAX_COLOR)

def parse_path(path, exc_table):
    local_path = path.relative_to(ROOT_PATH)
    path_parts = local_path.parts
    iwad = path_parts[0]
    if len(path_parts) > 2: #NOTE: this assumes the pwad is directly under the iwad (might lean on this for MASTERLEVELS.WAD)
        pwad = path_parts[1]
    else:
        pwad = ""
    if [iwad, pwad] in exc_table.WAD_EXCEPTIONS:
        return #completely ignore
    parse_stats(path, iwad, pwad, exc_table)
    #TODO: if PRINT_ONCE_PER_WAD, then put blank lines between iwads, otherwise, put *two* blank lines between iwads
    if not PRINT_ONCE_PER_WAD:
        print() #when printing big level lists, put blank lines between wads

def _path_sort_key(path):
    local_path_parts = path.relative_to(ROOT_PATH).parts
    if len(local_path_parts) == 2: #iwads should sort before pwads
        local_path_parts = (local_path_parts[0], "", local_path_parts[1])
    return local_path_parts

def main():
    with open(EXCEPTIONS_FILE, 'rb') as exc_file:
        exc_table_raw = tomllib.load(exc_file)
    exc_table = Exceptions_Table(**exc_table_raw)
    for path in sorted(ROOT_PATH.rglob("stats.txt"), key=_path_sort_key):
        parse_path(path, exc_table)
    cprint(f"Total maps maxed: {TOTAL_MAXED_LVLS}", TOTALS_COLOR)
    cprint(f"Total dead demons: {TOTAL_DEAD_DEMONS}", TOTALS_COLOR)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Shows for each WAD whether you've maxed it, or what level you need to max next.",
        epilog="You can define exceptions to the default behavior in exceptions.toml."
    )
    parser.add_argument("-v", "--verbose", help="show stats for every unmaxed map", action="store_false")
    parser.add_argument("-i", "--items", help="require 100%% items for max criteria", action="store_true")
    args = parser.parse_args()
    PRINT_ONCE_PER_WAD = args.verbose
    REQUIRE_ITEMS = args.items
    TOTAL_MAXED_LVLS = 0
    TOTAL_DEAD_DEMONS = 0
    main()
