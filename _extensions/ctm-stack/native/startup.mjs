// SPDX-License-Identifier: AGPL-3.0-or-later
export function startup(adapter, classified) {
  return adapter + [
    'ctm_emit(s):=printf(true,"~%~a~%",s)$', 'display2d:false$',
    'maxima_userdir:"/ctm"$',
    'load("/ctm/moodle-qtype_stack-master/stack/maxima/stacklocallinux.mac")$',
    'display2d:false$', 'linel:1000000$', ':lisp ' + classified.trim(),
    'ctm_emit(sconcat("CTMSTACK-READY|",stackmaximaversion,"|",MAXIMA_VERSION_STR))$', '',
  ].join('\n');
}
