#!/usr/bin/env python3
import sys
import os
import subprocess
import signal
import time
import sqlite3
import argparse
from functools import partial
from datetime import datetime
from contextlib import contextmanager

# good old fashioned relational databases <3
ROOT_DIR = os.path.expanduser("~/.superslots/")
SQLITE_DB = os.path.join(ROOT_DIR, "register.db")

os.makedirs(ROOT_DIR, exist_ok=True)

conn = sqlite3.connect(SQLITE_DB)

# send USR1 signal to process with given pid
def sigusr1(pid, slot):
    try:
        os.kill(pid, signal.SIGUSR1)
        return "ok"
    except ProcessLookupError:
        # Seems hacky to query inside a 'postgres-defined' function (below).. but seems work...
        with conn:
            conn.execute('delete from register where pid = (?) and slot = (?);', (pid,slot))
        return "fail"

def sigusr2(pid, slot):
    return 0

def db_print(args):
    print(">>> Listing all waiters and their slots")
    with conn:
        for r in conn.execute("select * from register"):
            print(">>> PID: {0}, slot: '{1}', cmd: '{2}', created: '{3}'".format(*r))
    return 0

def db_drop(args):
    print(">>> Dropping the whole database..")
    with conn:
        conn.execute("DROP TABLE IF EXISTS register;")
    return 0

def db_init_maybe():
    q = """
    CREATE TABLE IF NOT EXISTS register (
            pid INTEGER NOT NULL CHECK (pid > 1),
            slot TEXT NOT NULL,
            command TEXT NOT NULL,
            created DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            PRIMARY KEY (pid, slot)
    );
    """
    with conn:
        conn.execute(q)
        conn.create_function("sigusr1", 2, sigusr1)
        conn.create_function("sigusr2", 2, sigusr2)


@contextmanager
def register(slot, cmd, pid):
    cmd = ' '.join(cmd)
    qins = "INSERT OR REPLACE INTO REGISTER (pid, slot, command) VALUES (?, ?, ?)"
    qdel = "DELETE FROM register WHERE pid = (?) AND slot = (?)"
    m    = ">>> PID {1}: {2}register on slot '{0}'"

    print(m.format(slot, pid, ""), "command: '{0}'".format(cmd))
    with conn: conn.execute(qins, (pid, slot, cmd))
    yield
    with conn: conn.execute(qdel, (pid, slot))
    print(m.format(slot, pid, "de"))


#True Some processes might get killed before they can call deregister()
# This can clean up old pid's manually...
def cleanup(args):
    q = """
    DELETE FROM
        register
    WHERE
        (julianday(CURRENT_TIMESTAMP) - julianday(created)) * 24.0 >= 1
    ;
    """
    with conn:
        conn.execute(q)
    # fuck it, just drop the table with an extra argv flag?

# Reliest on python-defined sigusr1 function, see db_init_maybe().
def trigger(args):
    print(">>> trigger:", args.slot)
    with conn:
        q = """
        SELECT
            pid, sigusr1(pid,slot)
        FROM
            register
        WHERE
            slot = (?)
        AND
            ((julianday(CURRENT_TIMESTAMP) - julianday(created)) * 24.0 < 1)
        ;
        """
        results = list(conn.execute(q, (args.slot,)))

        if len(results) == 0:
            print(">>> No one was listening on slot '{0}'".format(args.slot))

        for pid, status in results:
            print(">>> sigusr1(pid = {0}) -> {1}".format(pid, status))

    return 0


running = True
runUSR1 = False
runUSR2 = False

def sigint_handler(signum, stack):
    global running
    print(">>> Quitting..")
    running = False

def sigusr1_handler(signum, stack):
    global runUSR1
    runUSR1 = True

def sigusr2_handler(signum, stack):
    global runUSR2
    runUSR2 = True

def handler_setup():
    signal.signal(signal.SIGINT,  sigint_handler)
    signal.signal(signal.SIGTERM, sigint_handler)
    signal.signal(signal.SIGUSR1, sigusr1_handler)
    signal.signal(signal.SIGUSR2, sigusr2_handler)


#def waitfor(slot, cmd, special=False, keepalive=False):
def waitfor(args):
    global running, runUSR1
    func = partial(subprocess.run, args.cmd[0] if args.special else args.cmd,
            shell=args.special, check=False)
    pid = os.getpid()

    with register(args.slot, args.cmd, pid):
        print(">>> PID {0}: Waiting on slot '{1}' to run: {2}".format(pid, args.slot, args.cmd))
        while running:
            t = datetime.strftime(datetime.now(), "%H:%M:%S")
            print(">>> @{0} PID {1}: Waiting...".format(t, pid))
            signal.pause()
            time.sleep(0.3) # Wait that flags might be changed... Not very good code..
            if not runUSR1:
                continue
            try:
                p = func()
            except FileNotFoundError:
                print(">>>!! ERROR: 'FileNotFoundError', is your command correct? Perhaps you need --special flag?")
                return -1
            if p.returncode != 0 and not args.keepalive:
                print(">>> Got errors and no --keepalive specified -> dropping out of wait loop. Check your command for errors!")
                return p.returncode
            runUSR1 = False

    return 0


def main(args):
    db_init_maybe()

    handler_setup()

    # There is a disconnect between the keys here and the subcommands specified in
    # argument parser definition
    fns = {"reset": db_drop, "list": db_print, "wait": waitfor, "trigger": trigger}

    return fns[args.subcommand](args)


def parseargs(argv):
    parser = argparse.ArgumentParser(
        description="Setup a command to be run when signaled on a named slot",
        epilog='\n'.join([
            "Example:",
            "    %(prog)s wait --keepalive myslot1 -- make -j4",
            "    %(prog)s wait --special   myslot2 -- 'ls | sort'",
            "",
            "Then trigger in another window:",
            "    %(prog)s trigger myslot1",
            "",
            "Now 'make -j4' runs in the first terminal",
            "",
            "NOTE: any non-arguments must come AFTER the <slot>"]),
        formatter_class = argparse.RawTextHelpFormatter,
    )

    subparser = parser.add_subparsers(title="Available subcommands",
        help="run <subcommand> --help",
        dest="subcommand",
    )
    subparser.required = True

    reset = subparser.add_parser("reset", epilog="Drops the current database. Can be useful.")
    listp = subparser.add_parser("list")
    trigg = subparser.add_parser("trigger")
    wait  = subparser.add_parser("wait")

    reset.add_argument('--yes-really', required=True, action="store_true")

    trigg.add_argument("slot", metavar='<slot>',
        help="Processes waiting on this <slot> are signaled",
    )

    wait.add_argument(
        "--keepalive",
        help="Don't exit even if external program 'fails' (useful with 'make', for example)",
        action='store_true'
    )
    wait.add_argument(
        "--special",
        help="Command is a string and needs to be ran through a shell.",
        action='store_true'
    )
    wait.add_argument("slot", metavar='<slot>',
        help="Which slot is waited on. This can be any ordinary ASCII-string"
    )
    wait.add_argument('cmd', metavar='<...>',
        help="External command in the form of a string or a list of arguments. See --special.",
        nargs=argparse.REMAINDER
    )

    # If you fuck up and include e.g --keepalive after <slot>, then there is no way to determine if
    # its actually meant for this script or the other command that you are invoking later

    args = parser.parse_args(argv[1:])

    if args.subcommand == "wait" and not args.cmd:
        wait.error("\n\tAt least one non-argument command (or string) must be supplied after slot name")

    return args

if __name__ == "__main__":
    args = parseargs(sys.argv)
    sys.exit(main(args))
