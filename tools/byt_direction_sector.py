"""4170E0 integer direction sectors; strict boundaries and native lookup values."""


def sector(x,y,count):
    # VM28 passes signed-byte coordinates. Do not extend this API to arbitrary
    # words without checking the native partial-register arithmetic.
    if not(-128<=x<=127 and -128<=y<=127):raise ValueError('Expected signed byte vector')
    a=-y
    if count==4:
        signature=int(a>x)+2*int(a<-x)
        return (2,3,1,0)[signature]
    if count==8:
        comparisons=(2*a>x,a>2*x,2*a>-x,a>-2*x)
        table={0:4,2:5,3:6,7:7,8:3,12:2,13:1,15:0}
    elif count==12:
        comparisons=(a>4*x,a>x,4*a>x,4*a>-x,a>-x,a>-4*x)
        table={0:6,1:7,3:8,7:9,15:10,31:11,32:5,48:4,56:3,60:2,62:1,63:0}
    elif count==16:
        comparisons=(a>5*x,5*a>7*x,7*a>5*x,5*a>x,5*a>-x,7*a>-5*x,5*a>-7*x,a>-5*x)
        table={0:8,1:9,3:10,7:11,15:12,31:13,63:14,127:15,128:7,192:6,224:5,240:4,248:3,252:2,254:1,255:0}
    else:return 0
    signature=sum(int(value)<<index for index,value in enumerate(comparisons))
    return table.get(signature,0)
