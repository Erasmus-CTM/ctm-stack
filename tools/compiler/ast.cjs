// SPDX-License-Identifier: AGPL-3.0-or-later AND GPL-3.0-or-later
// Data nodes for the JavaScript actions in STACK's pinned PEG grammars.
// Node fields preserve structure/positions; author source is never reprinted
// through JavaScript floating point numbers.
class MPNode { constructor() { this.kind = this.constructor.name; } }
class MPAtom extends MPNode { constructor(value) { super(); this.value = value; } }
class MPInteger extends MPAtom {}
class MPFloat extends MPAtom { constructor(value,original) { super(value); this.original=original; } }
class MPString extends MPAtom {}
class MPBoolean extends MPAtom {}
class MPIdentifier extends MPAtom {}
class MPComment extends MPAtom { constructor(value,annotations) { super(value); this.annotations=annotations; } }
class MPAnnotation extends MPNode { constructor(type,params) { super(); this.type=type; this.params=params; } }
class MPOperation extends MPNode { constructor(op,lhs,rhs) { super(); this.op=op; this.lhs=lhs; this.rhs=rhs; } }
class MPPrefixOp extends MPNode { constructor(op,rhs) { super(); this.op=op; this.rhs=rhs; } }
class MPPostfixOp extends MPNode { constructor(op,lhs) { super(); this.op=op; this.lhs=lhs; } }
class MPFunctionCall extends MPNode { constructor(name,args) { super(); this.name=name; this.args=args; } }
class MPGroup extends MPNode { constructor(items) { super(); this.items=items; } }
class MPList extends MPGroup {}
class MPSet extends MPGroup {}
class MPIndexing extends MPNode { constructor(target,indices) { super(); this.target=target; this.indices=indices; } }
class MPIf extends MPNode { constructor(conditions,branches) { super(); this.conditions=conditions; this.branches=branches; } }
class MPLoop extends MPNode { constructor(body,configuration) { super(); this.body=body; this.configuration=configuration; } }
class MPLoopBit extends MPNode { constructor(mode,parameter) { super(); this.mode=mode; this.parameter=parameter; } }
class MPEvaluationFlag extends MPNode { constructor(identifier,value) { super(); this.identifier=identifier; this.value=value; } }
class MPStatement extends MPNode { constructor(expression,flags) { super(); this.expression=expression; this.flags=flags; } }
class MPRoot extends MPGroup {}
class CTPNode { constructor() { this.kind=this.constructor.name; } }
class CTPRoot extends CTPNode { constructor(children) { super(); this.children=children; } }
class CTPRaw extends CTPNode { constructor(value) { super(); this.value=value; } }
class CTPString extends CTPRaw { constructor(value,quoted) { super(value); this.quoted=quoted; } }
class CTPIOBlock extends CTPNode { constructor(channel,variable) { super(); this.channel=channel; this.variable=variable; } }
class CTPBlock extends CTPNode { constructor(name,params,children) { super(); this.name=name; this.params=params; this.children=children; } }
