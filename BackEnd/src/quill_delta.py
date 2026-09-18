import copy
import quill_op as op

NULL_CHARACTER = chr(0)
DIFF_EQUAL = 0
DIFF_INSERT = 1
DIFF_DELETE = -1


class Delta(object):
    def __init__(self, ops=None, **attrs):
        if hasattr(ops, 'ops'):
            ops = ops.ops
        self.ops = ops or []
        self.__dict__.update(attrs)

    def __eq__(self, other):
        return self.ops == other.ops

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, self.ops)

    def insert(self, text, **attrs):
        if text == "":
            return self
        new_op = {'insert': text}
        if attrs:
            new_op['attributes'] = attrs
        return self.push(new_op)

    def delete(self, length):
        if length <= 0:
            return self
        return self.push({'delete': length});

    def retain(self, length, **attrs):
        if length <= 0:
            return self
        new_op = {'retain': length}
        if attrs:
            new_op['attributes'] = attrs
        return self.push(new_op)

    def push(self, operation):
        index = len(self.ops)
        new_op = copy.deepcopy(operation)
        try:
            last_op = self.ops[index - 1]
        except IndexError:
            self.ops.append(new_op)
            return self
        
        if op.type(new_op) == op.type(last_op) == 'delete':
            last_op['delete'] += new_op['delete']
            return self

        if op.type(last_op) == 'delete' and op.type(new_op) == 'insert':
            index -= 1
            try:
                last_op = self.ops[index - 1]
            except IndexError:
                self.ops.insert(0, new_op)
                return self

        if new_op.get('attributes') == last_op.get('attributes'):
            if isinstance(new_op.get('insert'), str) and isinstance(last_op.get('insert'), str):
                last_op['insert'] += new_op['insert']
                return self

            if isinstance(new_op.get('retain'), int) and isinstance(last_op.get('retain'), int):
                last_op['retain'] += new_op['retain']
                return self

        self.ops.insert(index, new_op)
        return self
