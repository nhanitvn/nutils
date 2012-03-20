from . import util, element, numpy, _

class Zero( int ):
  'zero'

  shape = ()

  def __new__( cls ):
    'constructor'

    return int.__new__( cls, 0 )

  def __getitem__( self, item ):
    'getitem'

    return self

  def sum( self, axes ):
    'sum'

    return self

ZERO = Zero()

def align_shapes( func1, func2 ):
  'align shapes'

  if not isinstance( func1, ArrayFunc ):
    func1 = numpy.asarray( func1 )
  if not isinstance( func2, ArrayFunc ):
    func2 = numpy.asarray( func2 )

  D = len(func1.shape) - len(func2.shape)
  nul = (nulaxis,)
  shape = []
  for sh1, sh2 in zip( nul*-D + func1.shape, nul*D + func2.shape ):
    if sh1 is nulaxis:
      shape.append( sh2 )
    elif sh2 is nulaxis:
      shape.append( sh1 )
    else:
      assert sh1 == sh2, 'incompatible dimensions: %s and %s' % ( func1.shape, func2.shape )
      shape.append( sh1 )
  return shape

def is_zero( obj ):
  'check if equals zero'

  if obj is ZERO:
    return True

  if isinstance( obj, numpy.ndarray ):
    return ( obj == 0 ).all()

  return obj == 0

def is_unit( obj ):
  'check if equals one'

  if isinstance( obj, numpy.ndarray ):
    return obj.ndim == 0 and obj == 1

  return obj == 1

class UsableArray( numpy.ndarray ):
  'array wrapper that can be compared'

  def __new__( cls, array ):
    'new'

    return numpy.asarray( array ).view( cls )

  def __eq__( self, other ):
    'compare'

    return self is other \
        or isinstance( other, numpy.ndarray ) \
       and other.shape == self.shape \
       and numpy.ndarray.__eq__( self, other ).all()

def normdim( length, n ):
  'sort and make positive'

  return sorted( ni + length if ni < 0 else ni for ni in n )

class StackIndex( int ):
  'stack index'

  def __str__( self ):
    'string representation'

    return '%%%d' % self

class NulAxis( int ):
  'nul axis'

  __new__ = lambda cls: int.__new__( cls, 1 )

nulaxis = NulAxis()

class Evaluable( object ):
  'evaluable base classs'

  operations = None
  needxi = False

  def recurse_index( self, operations ):
    'compile'

    for i, (op,idx) in enumerate( operations ):
      if op == self:
        return StackIndex( i )

    indices = [ arg.recurse_index( operations ) if isinstance( arg, Evaluable ) else arg for arg in self.args ]
    operations.append(( self, indices ))
    return StackIndex( len(operations)-1 )

  def compile( self ):
    'compile'

    if self.operations is None:
      self.operations = []
      self.recurse_index( self.operations ) # compile expressions
      
  def __call__( self, xi ):
    'evaluate'

    self.compile()
    values = []
    try:
      for op, arglist in self.operations:
        args = [ values[arg] if isinstance( arg, StackIndex ) else arg for arg in arglist ]
        values.append( op.eval( xi, *args ) if op.needxi else op.eval( *args ) )
    except:
      self.printstack( pointer=(op,arglist), values=values )
      raise
    #self.printstack( values=values ) # DEBUG
    #raw_input('press enter to continue')
    return values[-1]

  def printstack( self, pointer=None, values=None ):
    'print stack'

    self.compile()
    print 'call stack:'
    for i, (op,arglist) in enumerate( self.operations ):
      try:
        code = op.eval.func_code
        names = code.co_varnames[ :code.co_argcount ]
        if op.needxi:
          names = names[1:]
        names += tuple( '%s[%d]' % ( code.co_varnames[ code.co_argcount ], i ) for i in range( len(arglist) - len(names) ) )
      except:
        args = [ util.obj2str(arg) for arg in arglist ]
      else:
        args = [ '%s=%s' % ( name, util.obj2str(arg) ) for name, arg in zip( names, arglist ) ]
      shape = ' = ' + util.obj2str( values[i] ) if values and len( values ) > i else ''
      arrow = ' <-----ERROR' if pointer and pointer[0] is op and pointer[1] is arglist else ''
      print '%2d: %s( %s )%s%s' % ( i, op.__class__.__name__, ', '.join( args ), shape, arrow )

  def __eq__( self, other ):
    'compare'

    return self is other or ( self.__class__ == other.__class__ and self.args == other.args )

class Tuple( Evaluable ):
  'combine'

  def __init__( self, args ):
    'constructor'

    self.args = tuple( args )

  @staticmethod
  def eval( *f ):
    'evaluate'

    return f

# ARRAY FUNCTIONS

def merge( func0, *funcs ): # temporary
  'merge disjoint function spaces into one'

  assert func0.__class__ is Function
  shape = func0.shape
  mapping = func0.mapping.copy()
  nelems = len( func0.mapping )
  isfuncsp = shape and isinstance( shape[0], DofAxis )
  if isfuncsp:
    dofmap = shape[0].mapping.copy()
    ndofs = int(shape[0])
    shape = shape[1:]
  for func in funcs:
    assert func.__class__ is Function
    if func.shape and isinstance( func.shape[0], DofAxis ):
      assert isfuncsp and func.shape[1:] == shape
      dofmap.update( (elem,idx+ndofs) for (elem,idx) in func.shape[0].mapping.iteritems() )
      ndofs += int(func.shape[0])
    else:
      assert not isfuncsp and func.shape == shape
    mapping.update( func.mapping )
    nelems += len( func.mapping )
  assert nelems == len( mapping ), 'duplicate elements'
  if isfuncsp:
    shape = ( DofAxis(ndofs,dofmap), ) + shape
  return Function( shape, mapping )

class ArrayFunc( Evaluable ):
  'array function'

  def __getitem__( self, item ):
    'get item'
  
    if not isinstance( item, tuple ):
      item = ( item, )
    if Ellipsis in item:
      idx = item.index( Ellipsis )
      n = len(item) - item.count(_) - 1
      item = item[:idx] + (slice(None),)*(len(self.shape)-n) + item[idx+1:]
      assert Ellipsis not in item
    assert len(item) - item.count(_) == len(self.shape)
    shape = []
    itershape = iter( self.shape )
    for it in item:
      if it == _:
        shape.append( nulaxis )
        continue
      sh = itershape.next()
      if isinstance( sh, int ) and isinstance( it, int ):
        assert it < sh, 'index out of bounds'
      elif isinstance( it, (list,tuple) ):
        assert all( i < sh for i in it ), 'index out of bounds'
        shape.append( len(it) )
      elif it == slice(None):
        shape.append( sh )
      elif isinstance( sh, int ) and isinstance( it, slice ):
        shape.append( len( numpy.arange(sh)[it] ) )
      else:
        raise Exception, 'invalid slice item: %r' % it
    return GetItem( self, tuple(shape), item )

  def __iter__( self ):
    'split first axis'

    return ( self[i] for i in range(self.shape[0]) )

# def transform( self, transformation, axis ):
#   'transform'

#   assert len(transformation.shape) == 2
#   if axis >= 0:
#     axis -= len(self.shape)
#   tail = -1 - axis
#   return Dot( self[(Ellipsis,_)+(slice(None),)*tail],
#               transformation[(Ellipsis,)+(_,)*tail], (axis,) )

  def normal( self, topo ):
    'normal'

    grad = self.localgradient( topo )
    if grad.shape == (2,1):
      normal = Concatenate([ grad[1,:], -grad[0,:] ])
    elif grad.shape == (3,2):
      normal = Cross( grad[:,0], grad[:,1], axis=0 )
#   elif grad.shape[:2] == (3,1):
#     normal = numpy.cross( grad.next.normal.T, grad[:,0,:].T ).T
    else:
      raise NotImplementedError, 'cannot compute normal for %dx%d jacobian' % grad.shape
    return normal / normal.norm2(0)

  def dot( self, weights ):
    'dot'

    return StaticDot( self, weights )

  def inv( self ):
    'inverse'

    return Inverse( self )

  def swapaxes( self, n1, n2 ):
    'swap axes'

    return SwapAxes( self, n1, n2 )

  def grad( self, coords, topo ):
    'gradient'

    assert len(coords.shape) == 1
    return ( self.localgradient(topo)[...,_] * coords.localgradient(topo).inv() ).sum( -2 )
    #return self.localgradient(topo).transform( coords.localgradient(topo).inv(), -1 )

  def symgrad( self, coords, topo ):
    'gradient'

    g = self.grad( coords, topo )
    return .5 * ( g + g.swapaxes(-2,-1) )

  def div( self, coords, topo ):
    'gradient'

    return self.grad( coords, topo ).trace( -1, -2 )

  def ngrad( self, coords, topo ):
    'normal gradient'

    return ( self.grad(coords,topo) * coords.normal(topo.boundary) ).sum()

  def nsymgrad( self, coords, topo ):
    'normal gradient'

    return ( self.symgrad(coords,topo) * coords.normal(topo.boundary) ).sum()

  def norm2( self, axis ):
    'norm2'

    return Norm2( self, axis )

  def det( self, ax1, ax2 ):
    'determinant'

    return Determinant( self, ax1, ax2 )

  def __mul__( self, other ):
    'multiply'
  
    if is_zero(other):
      return ZERO

    if is_unit(other):
      return self

    if not isinstance( other, Evaluable ):
      other = numpy.asarray( other )
      if other.ndim:
        other = StaticArray( other )

    return Multiply( self, other )

  def __div__( self, other ):
    'multiply'
  
    assert not is_zero(other)

    if is_unit(other):
      return self

    if not isinstance( other, Evaluable ):
      other = numpy.asarray( other )
      if other.ndim:
        other = StaticArray( other )

    return Divide( self, other )

  def __add__( self, other ):
    'add'

    if is_zero(other):
      return self

    if not isinstance( other, Evaluable ):
      other = numpy.asarray( other )
      if other.ndim:
        other = StaticArray( other )

    return Add( self, other )

  __rmul__ = __mul__
  __radd__ = __add__

  def __sub__( self, other ):
    'subtract'
  
    if other == 0:
      return self
    return Subtract( self, other )

  def __neg__( self ):
    'negate'

    return Negate( self )

  @property
  def T( self ):
    'transpose'

    assert len(self.shape) == 2
    return SwapAxes( self, 0, 1 )

  def symmetric( self, n1, n2 ):
    'symmetric'

    return Symmetric( self, n1, n2 )

  def trace( self, n1, n2 ):
    'symmetric'

    return Trace( self, n1, n2 )

class StaticDot( ArrayFunc ):
  'dot with static array'

  def __init__( self, func, array ):
    'constructor'

    array = UsableArray( array )
    dofaxis = func.shape[0]
    assert isinstance( dofaxis, DofAxis )
    assert int(dofaxis) == array.shape[0]
    shape = array.shape[1:] + func.shape[1:]

    self.func = func
    self.array = array
    self.shape = tuple(shape)
    self.args = func, array, dofaxis

  @staticmethod
  def eval( func, array, I ):
    'evaluate'

    return numpy.tensordot( array[I], func, (0,0) )

  def localgradient( self, topo ):
    'local gradient'

    return StaticDot( self.func.localgradient(topo), self.array )

  def __mul__( self, other ):
    'multiply'

    if isinstance( other, (int,float) ):
      return StaticDot( self.func, self.array * other )

    return ArrayFunc.__mul__( self, other )

  def __add__( self, other ):
    'add'

    if isinstance( other, StaticDot ) and other.func == self.func:
      return StaticDot( self.func, self.array + other.array )

    return ArrayFunc.__add__( self, other )

class Function( ArrayFunc ):
  'function'

  needxi = True

  def __init__( self, shape, mapping ):
    'constructor'

    self.shape = shape
    self.mapping = mapping
    self.args = mapping,

  @staticmethod
  def eval( xi, fmap ):
    'evaluate'

    while xi.elem not in fmap:
      xi = xi.next
    return fmap[ xi.elem ].eval( xi.points )

  def vector( self, ndims ):
    'vectorize'

    return Vectorize( [self]*ndims )

  def localgradient( self, topo ):
    'local derivative'

    return LocalGradient( self, topo )

  def __str__( self ):
    'string representation'

    return 'Function:%x' % id(self.mapping)

class PieceWise( ArrayFunc ):
  'differentiate by topology'

  needxi = True

  def __init__( self, *func_and_topo ):
    'constructor'
    
    assert func_and_topo and len(func_and_topo) % 2 == 0
    fmap = {}
    args = ()
    shape = ()
    for topo, func in reversed( zip( func_and_topo[::2], func_and_topo[1::2] ) ):
      if not isinstance( func, ArrayFunc ):
        assert isinstance( func, (numpy.ndarray,int,float,list,tuple) )
        func = StaticArray( func )
      n = len(shape) - len(func.shape)
      if n < 0:
        assert shape == func.shape[-n:]
        shape = func.shape
      else:
        assert func.shape == shape[n:]
      n = len(args)
      args += func.args
      s = slice(n,len(args))
      fmap.update( dict.fromkeys( topo, (func,s) ) )
    self.args = (fmap,)+args
    self.shape = shape

  @staticmethod
  def eval( xi, fmap, *args ):
    'evaluate'

    while xi.elem not in fmap:
      xi = xi.next
    func, s = fmap[ xi.elem ]
    return func.eval( xi, *args[s] ) if func.needxi else func.eval( *args[s] )

class Inverse( ArrayFunc ):
  'inverse'

  def __init__( self, func ):
    'constructor'

    assert len(func.shape) == 2 and func.shape[0] == func.shape[1]
    self.args = func, (0,1)
    self.shape = func.shape

  eval = staticmethod( util.inv )

class DofAxis( ArrayFunc ):
  'dof axis'

  needxi = True

  def __init__( self, ndofs, mapping ):
    'new'

    self.ndofs = ndofs
    self.mapping = mapping
    self.get = mapping.get
    self.args = mapping,
    self.shape = ndofs,

  @staticmethod
  def eval( xi, idxmap ):
    'evaluate'

    index = idxmap.get( xi.elem )
    while index is None:
      xi = xi.next
      index = idxmap.get( xi.elem )
    return index

  def __eq__( self, other ):
    'equals'

    if self is other:
      return True

    if not isinstance( other, DofAxis ):
      return False
      
    if set(self.mapping) != set(other.mapping):
      return False

    for elem in self.mapping:
      if list(self.mapping[elem]) != list(other.mapping[elem]):
        return False

    return True

  def __add__( self, other ):
    'add'

    if other == 0:
      return self

    assert isinstance( other, DofAxis )

    #mapping = self.mapping.copy()
    #for elem, idx2 in other.mapping.iteritems():
    #  idx1 = mapping.get( elem )
    #  mapping[ elem ] = idx2 + self.ndofs if idx1 is None \
    #               else numpy.hstack([ idx1, idx2 + self.ndofs ])
    #return DofAxis( self.ndofs + other.ndofs, mapping )

    other_mapping = other.mapping.copy()
    try:
      mapping = dict( ( elem, numpy.hstack([ idx, other_mapping.pop(elem) + self.ndofs ]) )
                        for elem, idx in self.mapping.iteritems() )
    except KeyError, e:
      raise Exception, 'element not in other: %s' % e.args[0]
    if other_mapping:
      raise Exception, 'element not in self: %s' % other_mapping.popitem()[0]

    return DofAxis( self.ndofs + other.ndofs, mapping )

  __radd__ = __add__

  def __int__( self ):
    'int'

    return self.ndofs

  def __repr__( self ):
    'string representation'

    return 'DofAxis(%d)' % self

class Concatenate( ArrayFunc ):
  'concatenate'

  def __init__( self, funcs, axis=0 ):
    'constructor'

    self.args = (axis,) + tuple(funcs)
    self.shape = ( sum( func.shape[0] for func in funcs ), ) + funcs[0].shape[1:]

  def localgradient( self, topo ):
    'gradient'

    funcs = [ func.localgradient(topo) for func in self.args[1:] ]
    return Concatenate( funcs, axis=self.args[0] )

  @staticmethod
  def eval( axis, *funcs ):
    'evaluate'

    return numpy.concatenate( funcs, axis=axis )

class Vectorize( ArrayFunc ):
  'vectorize'

  def __init__( self, funcs ):
    'constructor'

    self.args = tuple( funcs )
    self.shape = ( sum( func.shape[0] for func in funcs ), len(funcs) ) + funcs[0].shape[1:]

  @staticmethod
  def eval( *funcs ):
    'evaluate'

    N = sum( func.shape[0] for func in funcs )
    shape = ( N, len(funcs) ) + funcs[0].shape[1:]
    data = numpy.zeros( shape )
    count = 0
    for i, func in enumerate( funcs ):
      n = func.shape[0]
      data[count:count+n,i] = func
      count += n
    assert count == N
    return data

  def localgradient( self, topo ):
    'gradient'

    return Vectorize([ func.localgradient(topo) for func in self.args ])

  def trace( self, n1, n2 ):
    'trace'

    n1, n2 = normdim( len(self.shape), (n1,n2) )
    assert self.shape[n1] == self.shape[n2]
    if n1 == 1 and n2 == 2:
      trace = Concatenate([ func[:,idim] for idim, func in enumerate( self.args ) ])
    else:
      trace = Trace( self, n1, n2 )
    return trace

  def dot( self, weights ):
    'dot'

    if all( func == self.args[0] for func in self.args[1:] ):
      return self.args[0].dot( weights.reshape( len(self.args), -1 ).T )

    n1 = 0
    funcs = []
    for func in self.args:
      n0 = n1
      n1 += int(func.shape[0])
      funcs.append( func.dot( weights[n0:n1,_] ) )
    return Concatenate( funcs )

class Stack( ArrayFunc ):
  'stack'

  def __init__( self, funcs ):
    'constructor'

    funcs = numpy.array( funcs, dtype=object )
    flatfuncs = tuple( funcs.flat )
    shape = []
    indices = []
    partitions = []
    for idim in range( funcs.ndim ):
      n1 = 0
      index = []
      slices = []
      for n in range( funcs.shape[idim] ):
        f = None
        for func in funcs.take( [n], axis=idim ).flat:
          if isinstance( func, ArrayFunc ) and func.shape[idim] is not nulaxis:
            if not f:
              f = func
            else:
              assert f.shape[idim] == func.shape[idim]
        assert f is not None, 'no ArrayFuncs found in row/column'
        index.append( flatfuncs.index(f) )
        n0 = n1
        n1 += f.shape[idim]
        slices.append( slice(n0,n1) )
      indices.append( index )
      shape.append( n1 )
      partitions.append( slices )
    f = None
    for func in funcs.flat:
      if isinstance( func, ArrayFunc ):
        if not f:
          f = func
        else:
          assert func.shape[funcs.ndim:] == f.shape[funcs.ndim:]
    shape.extend( f.shape[funcs.ndim:] )

    self.funcs = funcs
    self.args = (indices,) + flatfuncs
    self.shape = tuple(shape)
    self.partitions = partitions

  @staticmethod
  def eval( indices, *blocks ):
    'evaluate'

    shape = []
    partitions = []
    for idim, index in enumerate( indices ):
      n1 = 0
      slices = []
      for iblk in index:
        n0 = n1
        n1 += blocks[iblk].shape[idim]
        slices.append( slice(n0,n1) )
      shape.append( n1 )
      partitions.append( slices )

    stacked = numpy.empty( tuple(shape) + blocks[iblk].shape[len(shape):] )
    for I, block in zip( numpy.broadcast( *numpy.ix_( *partitions ) ) if len(partitions) > 1 else partitions[0], blocks ):
      stacked[ I ] = block
    return stacked

class UFunc( ArrayFunc ):
  'user function'

  def __init__( self, coords, ufunc, *gradients ):
    'constructor'

    self.coords = coords
    self.gradients = gradients
    self.shape = ufunc( numpy.zeros( coords.shape ) ).shape
    self.args = ufunc, coords

  @staticmethod
  def eval( f, x ):
    'evaluate'

    return f( x )

  def localgradient( self, topo ):
    'local gradient'

    raise NotImplementedError

  def grad( self, coords, topo ):
    'gradient'

    assert coords is self.coords # TODO check tole of topo arg
    return UFunc( self.coords, *self.gradients )

class LocalGradient( ArrayFunc ):
  'local gradient'

  needxi = True

  def __init__( self, func, topo ):
    'constructor'

    self.topo = topo
    self.shape = func.shape + (topo.ndims,)
    self.args = func.mapping, topo

  @staticmethod
  def eval( xi, fmap, topo ):
    'evaluate'

    while xi.elem not in topo:
      xi = xi.next
    T = 1
    while xi.elem not in fmap:
      xi = xi.next
      T = numpy.dot( T, xi.transform )
    F = fmap[ xi.elem ].eval( xi.points, grad=1 )
    return util.transform( F, T, axis=-2 )

class Norm2( ArrayFunc ):
  'integration weights'

  def __init__( self, fun, axis=0 ):
    'constructor'

    self.args = fun, axis
    shape = list( fun.shape )
    shape.pop( axis )
    self.shape = tuple(shape)

  @staticmethod
  def eval( fval, axis ):
    'evaluate'

    return numpy.sqrt( util.contract( fval, fval, axis ) )

class Cross( ArrayFunc ):
  'normal'

  def __init__( self, f1, f2, axis ):
    'contructor'

    assert f1.shape == f2.shape
    self.shape = f1.shape
    self.args = fun1, fun2, -1, -1, -1, axis

  eval = staticmethod( numpy.cross )

class Determinant( ArrayFunc ):
  'normal'

  def __init__( self, fun, ax1, ax2 ):
    'contructor'

    self.args = fun, ax1, ax2

  eval = staticmethod( util.det )

  def __str__( self ):
    'string representation'

    return '%s.det(%d,%d)' % self.args

class GetItem( ArrayFunc ):
  'get item'

  def __init__( self, func, shape, item ):
    'constructor'

    self.shape = shape
    self.args = func, item

  eval = staticmethod( numpy.ndarray.__getitem__ )

  def localgradient( self, topo ):
    'local gradient'

    func, item = self.args
    return func.localgradient( topo )[item+(slice(None),)]

  def __str__( self ):
    'string representation'

    return '%s[%s]' % ( self.args[0], ','.join( util.obj2str(arg) for arg in self.args[1] ) )

class StaticArray( ArrayFunc ):
  'static array'

  needxi = True

  def __init__( self, array, shape=None ):
    'constructor'

    array = UsableArray( array )
    self.args = array,
    if shape is None:
      shape = array.shape
    else:
      assert len(shape) == array.ndim
      for sh1, sh2 in zip( shape, array.shape ):
        assert int(sh1) == sh2
    self.shape = shape

  def __getitem__( self, item ):
    'get item'

    if not isinstance( item, tuple ):
      item = ( item, )
    if Ellipsis in item:
      idx = item.index( Ellipsis )
      n = len(item) - item.count(_) - 1
      item = item[:idx] + (slice(None),)*(len(self.shape)-n) + item[idx+1:]
      assert Ellipsis not in item

    iter_item = iter( item )
    shape = []
    array = self.args[0]
    for sh in self.shape:
      for it in iter_item:
        if it != _:
          break
        shape.append( nulaxis )
      if not isinstance( it, int ):
        shape.append( len( numpy.arange(sh)[it] ) )
    for it in iter_item:
      assert it == _
      shape.append( nulaxis )
    return StaticArray( array[item], tuple(shape) )

  def localgradient( self, topo ):
    'local gradient'

    return ZERO

  @staticmethod
  def eval( xi, array ):

    return util.appendaxes( array, xi.points.coords.shape[1:] )

  def __str__( self ):
    'string representation'

    return 'StaticArray(%s)' % self.args[0]

class Multiply( ArrayFunc ):
  'multiply'

  def __init__( self, func1, func2 ):
    'constructor'

    self.args = func1, func2
    self.shape = tuple( align_shapes( func1, func2 ) )

  eval = staticmethod( numpy.ndarray.__mul__ )

  def sum( self, ax1=-1, *axes ):
    'sum'

    func1, func2 = self.args
    return Dot( func1, func2, (ax1,)+axes )

  def localgradient( self, topo ):
    'gradient'

    return self.args[0][...,_] * self.args[1].localgradient(topo) \
         + self.args[1][...,_] * self.args[0].localgradient(topo)

  def __str__( self ):
    'string representation'

    return '%s * %s' % self.args

class Divide( ArrayFunc ):
  'divide'

  def __init__( self, func1, func2 ):
    'constructor'

    if not isinstance( func1, Evaluable ):
      func1 = numpy.asarray( func1 )
      if func1.ndim:
        func1 = StaticArray( func1 )
    if not isinstance( func2, Evaluable ):
      func2 = numpy.asarray( func2 )
      if func2.ndim:
        func2 = StaticArray( func2 )

    self.args = func1, func2
    D = len(func1.shape) - len(func2.shape)
    nul = (nulaxis,)
    shape = []
    for sh1, sh2 in zip( nul*-D + func1.shape, nul*D + func2.shape ):
      if sh1 is nulaxis:
        shape.append( sh2 )
      elif sh2 is nulaxis:
        shape.append( sh1 )
      else:
        assert sh1 == sh2, 'incompatible dimensions: %s and %s' % ( func1.shape, func2.shape )
        shape.append( sh1 )
    self.shape = tuple( shape )

  eval = staticmethod( numpy.ndarray.__div__ )

  def __str__( self ):
    'string representation'

    return '%s / %s' % self.args

class Negate( ArrayFunc ):
  'negate'

  def __init__( self, func ):
    'constructor'

    self.shape = func.shape
    self.args = func,

  eval = staticmethod( numpy.ndarray.__neg__ )

  def __str__( self ):
    'string representation'

    return '-%s' % self.args[0]

class Add( ArrayFunc ):
  'add'

  def __init__( self, func1, func2 ):
    'constructor'

    if isinstance( func1, (int,float) ):
      func1 = numpy.asarray( func1 )
    func1_shape = func1.shape

    if isinstance( func2, (int,float) ):
      func2 = numpy.asarray( func2 )
    func2_shape = func2.shape

    self.args = func1, func2
    D = len(func1_shape) - len(func2_shape)
    nul = (nulaxis,)
    shape = []
    for sh1, sh2 in zip( nul*-D + func1_shape, nul*D + func2_shape ):
      if sh1 is nulaxis:
        shape.append( sh2 )
      elif sh2 is nulaxis:
        shape.append( sh1 )
      else:
        assert sh1 == sh2, 'incompatible dimensions: %s and %s' % ( func1_shape, func2_shape )
        shape.append( sh1 )
    self.shape = tuple( shape )

  eval = staticmethod( numpy.ndarray.__add__ )

  def __str__( self ):
    'string representation'

    return '(%s + %s)' % self.args

class Subtract( ArrayFunc ):
  'subtract'

  def __init__( self, func1, func2 ):
    'constructor'

    if isinstance( func1, (int,float) ):
      func1 = numpy.asarray( func1 )
    func1_shape = func1.shape

    if isinstance( func2, (int,float) ):
      func2 = numpy.asarray( func2 )
    func2_shape = func2.shape

    self.args = func1, func2
    D = len(func1_shape) - len(func2_shape)
    nul = (nulaxis,)
    shape = []
    for sh1, sh2 in zip( nul*-D + func1_shape, nul*D + func2_shape ):
      if sh1 is nulaxis:
        shape.append( sh2 )
      elif sh2 is nulaxis:
        shape.append( sh1 )
      else:
        assert sh1 == sh2, 'incompatible dimensions: %s and %s' % ( func1_shape, func2_shape )
        shape.append( sh1 )
    self.shape = tuple( shape )

  eval = staticmethod( numpy.ndarray.__sub__ )

  def __str__( self ):
    'string representation'

    return '(%s - %s)' % self.args

class Dot( ArrayFunc ):
  'dot'

  def __init__( self, func1, func2, axes ):
    'constructor'

    shape = align_shapes( func1, func2 )
    axes = normdim( len(shape), axes )[::-1]
    for axis in axes:
      shape.pop( axis )

    self.args = func1, func2, tuple(axes)
    self.shape = tuple(shape)

  eval = staticmethod( util.contract )

  def localgradient( self, topo=None ):
    'local gradient'

    func1, func2, axes = self.args
    return ( func1.localgradient(topo) * func2[...,_] ).sum( *axes ) \
         + ( func1[...,_] * func2.localgradient(topo) ).sum( *axes )

  def __str__( self ):
    'string representation'

    return '(%s * %s).sum(%s)' % ( self.args[0], self.args[1], ','.join( str(n) for n in self.args[2] ) )

class SwapAxes( ArrayFunc ):
  'swapaxes'

  def __init__( self, func, n1, n2 ):
    'constructor'

    if n1 < 0:
      n1 += len(func.shape)
    if n2 < 0:
      n2 += len(func.shape)
    shape = list( func.shape )
    shape[n1] = func.shape[n2]
    shape[n2] = func.shape[n1]
    self.shape = tuple(shape)
    self.args = func, n1, n2

  eval = staticmethod( numpy.ndarray.swapaxes )

class Trace( ArrayFunc ):
  'trace'

  def __init__( self, func, n1, n2 ):
    'constructor'

    n1, n2 = normdim( len(func.shape), (n1,n2) )
    shape = list( func.shape )
    s1 = shape.pop( n2 )
    s2 = shape.pop( n1 )
    assert s1 == s2
    self.args = func, 0, n1, n2
    self.shape = tuple( shape )

  eval = staticmethod( numpy.ndarray.trace )

  def __str__( self ):
    'string representation'

    return '%s.trace(%d,%d)' % ( self.args[0], self.args[2], self.args[3] )

# MATHEMATICAL EXPRESSIONS

class UnaryFunc( ArrayFunc ):
  'unary base class'

  def __init__( self, func ):
    'constructor'

    self.args = func,
    self.shape = func.shape

  def __str__( self ):
    'string representation'

    return '%s(%s)' % ( self.__class__.__name__, self.args[0] )

class Exp( UnaryFunc ):
  'exponent'

  eval = staticmethod( numpy.exp )

  def localgradient( self, topo ):
    'gradient'

    return self * self.args[0].localgradient(topo)

class Sin( UnaryFunc ):
  'sine'

  eval = staticmethod( numpy.sin )

  def localgradient( self, topo ):
    'gradient'

    return Cos(self.args[0]) * self.args[0].localgradient(topo)
    
class Cos( UnaryFunc ):
  'cosine'

  eval = staticmethod( numpy.cos )

  def grad( self, coords, topo ):
    'gradient'

    return -Sin(self.args[0]) * self.args[0].grad(coords,topo)

class Log( UnaryFunc ):
  'cosine'

  eval = staticmethod( numpy.log )

#############################33

def RectilinearFunc( topo, gridnodes ):
  'rectilinear mesh generator'

  assert len( gridnodes ) == topo.ndims
  nodes_structure = numpy.empty( map( len, gridnodes ) + [topo.ndims] )
  for idim, inodes in enumerate( gridnodes ):
    shape = [1,] * topo.ndims
    shape[idim] = -1
    nodes_structure[...,idim] = numpy.asarray( inodes ).reshape( shape )

  return topo.linearfunc().dot( nodes_structure.reshape( -1, topo.ndims ) )

# def find( self, x, title=False ):
#   'find physical coordinates in all elements'

#   x = array.asarray( x )
#   assert x.shape[0] == self.topology.ndims
#   ielems = 0
#   coords = []
#   for xi, pi in zip( x, self.gridnodes ):
#     I = numpy.searchsorted( pi, xi )
#     coords.append( ( xi - pi[I-1] ) / ( pi[I] - pi[I-1] ) )
#     ielems = ielems * (len(pi)-1) + (I-1)
#   coords = numpy.array( coords )
#   elems = self.topology.structure.ravel()
#   indices = numpy.arange( len(ielems) )
#   if title:
#     progressbar = util.progressbar( n=indices.size, title=title )
#   while len( ielems ):
#     ielem = ielems[0]
#     select = ( ielems == ielem )
#     elem = elems[ ielem ]
#     xi = elem( coords[:,select] )
#     f = self( xi )
#     f.indices = indices[select]
#     yield f
#     ielems = ielems[~select]
#     coords = coords[:,~select]
#     indices = indices[~select]
#     if title:
#       progressbar.update( progressbar.n-indices.size-1 )

# vim:shiftwidth=2:foldmethod=indent:foldnestmax=2