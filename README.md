# superslots
Setup a command to be run when signaled on a named slot

# Details

Usage of this program is divided in two parts:

1) Registering a command to a slot. Do this with `./superslots.py wait <slot>`

2) Triggering a slot with `./superslots.py trigger <slot>`, causing all it's registered
   commands to be run.


# Usage
superslots.py has these subcommands:

`superslots.py list`

`superslots.py reset`

`superslots.py wait`

`superslots.py trigger`

Each of these has a separate --help page. Read them.

# Example:

    superslots.py wait --keepalive myslot1 -- ping -c2 localhost
    superslots.py wait --special   myslot2 -- 'ls | sort'

Then trigger in another window:
    `superslots.py trigger myslot1`

Now `ping` runs in the first terminal

NOTE: any non-arguments must come AFTER `<slot>`

# Hint:

1) In your OS's keyboard configuration, bind Ctrl+Shift+o (or something..) to run `superslots.py trigger build`

2) `cd` to your projects build dir

3) run `superslots.py wait --keepalive build -- make -j4`

4) Write code in another terminal, hit the key combo. Vuala! Your code compiles magically!

# Components/dependencies:

Python and Sqlite3. No other external dependencies.

Should work out-of-the-box with any *nix os. Uses signals in the trigger mechanism.

- python 3
    - argparse
    - subprocess
    - signal
    - time
    - os
    - functools
    - datetime
    - contextlib
- sqlite3

