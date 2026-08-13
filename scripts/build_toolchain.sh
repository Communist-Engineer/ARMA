#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_root="$project_root/build/toolchain/src"
binary_root="$project_root/build/toolchain/bin"

mkdir -p "$source_root" "$binary_root"

clone_at() {
  local repository=$1
  local commit=$2
  local target=$3
  if [[ ! -d "$target/.git" ]]; then
    git clone --filter=blob:none "$repository" "$target"
  fi
  git -C "$target" fetch --depth=1 origin "$commit"
  git -C "$target" checkout --detach "$commit"
  test "$(git -C "$target" rev-parse HEAD)" = "$commit"
}

clone_at https://github.com/arminbiere/cadical.git c60730422e758ef1cebe7aeddf2dda31c996bf04 "$source_root/cadical"
clone_at https://github.com/marijnheule/drat-trim.git 2e3b2dc0ecf938addbd779d42877b6ed69d9a985 "$source_root/drat-trim"
clone_at https://github.com/tanyongkiam/cake_lpr.git a36874a8b750b43fe4b385b8ddbf5b033e46a3fa "$source_root/cake_lpr"

# Normalize CaDiCaL's informational build string so the executable excludes the worker hostname.
sed -i 's/^OS=.*/OS="Linux x86_64"/' "$source_root/cadical/scripts/make-build-header.sh"

(
  cd "$source_root/cadical"
  make clean >/dev/null 2>&1 || true
  export SOURCE_DATE_EPOCH=1784475655
  ./configure --competition -static
  make -j2
  strip build/cadical
)
gcc "$source_root/drat-trim/drat-trim.c" -std=c99 -O2 -static \
  -o "$source_root/drat-trim/drat-trim"
strip "$source_root/drat-trim/drat-trim"
gcc -O2 "$source_root/cake_lpr/basis_ffi.c" "$source_root/cake_lpr/cake_lpr.S" \
  -o "$source_root/cake_lpr/cake_lpr" -std=c99 -static -Wl,-z,noexecstack
strip "$source_root/cake_lpr/cake_lpr"

install -m 0555 "$source_root/cadical/build/cadical" "$binary_root/cadical"
install -m 0555 "$source_root/drat-trim/drat-trim" "$binary_root/drat-trim"
install -m 0555 "$source_root/cake_lpr/cake_lpr" "$binary_root/cake_lpr"

sha256sum "$binary_root/cadical" "$binary_root/drat-trim" "$binary_root/cake_lpr"
