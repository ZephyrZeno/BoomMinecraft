"""Check the MASM net platform owner's real Winsock lifetime, without JNI claims."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from threading import Barrier, get_native_id
from uuid import uuid4
import winreg


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.boom'
spec=importlib.util.spec_from_file_location('net_platform_build_tools',ROOT/'scripts/nio-file-native-candidate.py')
N=importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)
S=N.S
P,U,Q=c.c_void_p,c.c_uint32,c.c_uint64
PREFIX='boom_builtin_net_platform_'
SOURCE=ROOT/'native/providers/builtin_net_platform.asm.inc'


def proc(image,name,result,*arguments):
    f=getattr(image,name)
    f.restype,f.argtypes=result,arguments
    return f


def fault_wrappers():
    # These wrappers are linked only into the separate fault-test DLL. The
    # production object keeps its direct, checked Win32/Winsock imports.
    text='''.data
ALIGN 8
PUBLIC fault_close_remaining
fault_close_remaining DWORD 0
PUBLIC fault_cleanup_remaining
fault_cleanup_remaining DWORD 0
PUBLIC fault_cleanup_attempts
fault_cleanup_attempts QWORD 0
PUBLIC fault_socket_creations
fault_socket_creations QWORD 0
PUBLIC fault_socket_closes
fault_socket_closes QWORD 0
EXTERN socket:PROC
EXTERN closesocket:PROC
EXTERN WSACleanup:PROC
EXTERN WSASetLastError:PROC
.code
fault_socket PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call socket
 cmp rax,-1
 je fault_socket_done
 lock inc QWORD PTR [fault_socket_creations]
fault_socket_done:
 add rsp,40
 ret
fault_socket ENDP
fault_closesocket PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 cmp DWORD PTR [fault_close_remaining],0
 je fault_close_real
 lock dec DWORD PTR [fault_close_remaining]
 mov ecx,10035
 call WSASetLastError
 mov eax,-1
 jmp fault_close_done
fault_close_real:
 call closesocket
 test eax,eax
 jnz fault_close_done
 lock inc QWORD PTR [fault_socket_closes]
fault_close_done:
 add rsp,40
 ret
fault_closesocket ENDP
fault_WSACleanup PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 lock inc QWORD PTR [fault_cleanup_attempts]
 cmp DWORD PTR [fault_cleanup_remaining],0
 je fault_cleanup_real
 lock dec DWORD PTR [fault_cleanup_remaining]
 mov ecx,10050
 call WSASetLastError
 mov eax,-1
 jmp fault_cleanup_done
fault_cleanup_real:
 call WSACleanup
fault_cleanup_done:
 add rsp,40
 ret
fault_WSACleanup ENDP
'''
    return text


def build(output,faults=False):
    output=output.resolve()
    S.check(output.is_relative_to(ART),'Keep platform tests inside project .boom')
    output.mkdir(parents=True,exist_ok=False)
    source=SOURCE.read_text()
    rebound={n:'fault_'+n for n in ('socket','closesocket','WSACleanup')} if faults else {}
    for name,replacement in rebound.items():
        source=re.sub(r'\b'+name+r'\b',replacement,source)
        source=source.replace('EXTERN '+replacement+':PROC\n','')
    assembly=output/'net-platform.asm'
    pools=''.join(f'PUBLIC net_platform_pool{i}\nnet_platform_pool{i} DWORD 04D54454Eh,2\n'
        ' QWORD 0\n DWORD 0,0,0,0,0,0,0,0\n QWORD 0,0,0\n DWORD 0,0\n' for i in range(2))
    assembly.write_text('option casemap:none\n'+source+(fault_wrappers() if faults else '')+
                        '\n.data\nALIGN 8\n'+pools+'END\n')
    tools=N.msvc()
    obj=output/'net-platform.obj'
    N.run([tools/'ml64.exe','/nologo','/c','/Fo'+str(obj),assembly],output,'assemble.log')
    imports={'AcquireSRWLockExclusive','ReleaseSRWLockExclusive','WSAStartup','WSACleanup','WSAGetLastError','socket','closesocket'}
    exports={PREFIX+n for n in ('start','acquire','release','close')}|{'net_platform_pool0','net_platform_pool1'}
    if faults:
        imports.add('WSASetLastError')
        exports.update(('fault_close_remaining','fault_cleanup_remaining','fault_cleanup_attempts',
                        'fault_socket_creations','fault_socket_closes'))
    S.check(N.A.coff_symbols(obj,imports)==(exports,imports),'Platform COFF has unexpected non-ASM or foreign dependencies')
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
        sdk=Path(winreg.QueryValueEx(key,'KitsRoot10')[0])
    [*_,kernel]=sorted((sdk/'Lib').glob('*/um/x64/kernel32.lib'),key=lambda p:tuple(map(int,p.parents[2].name.split('.'))))
    dll=output/'net-platform.dll'
    lines=['/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"']
    lines+=['"'+str(p)+'"' for p in (obj,kernel,kernel.with_name('synchronization.lib'),kernel.with_name('ws2_32.lib'))]
    lines+=['/EXPORT:'+name for name in sorted(exports)]
    response=output/'link.rsp'
    response.write_text('\n'.join(lines)+'\n')
    N.run([tools/'link.exe','@'+str(response)],output,'link.log')
    S.write(output/'image.json',dict(image=S.artifact(dll),assembly=S.artifact(assembly),object=S.artifact(obj),
        source=S.artifact(SOURCE),test_tool=S.artifact(Path(__file__)),imports=sorted(imports),exports=sorted(exports),
        pool_bytes=80,pool_abi=2,test_only_rebound_functions=rebound,
        JNI_OnLoad_implemented=False,NativeLibraries_load_completed=False,game_started=False))
    return dll


def execute(dll):
    image=c.CDLL(str(dll))
    ws=c.WinDLL('ws2_32.dll')
    sock=proc(ws,'socket',c.c_size_t,c.c_int,c.c_int,c.c_int)
    close_socket=proc(ws,'closesocket',c.c_int,c.c_size_t)
    last=proc(ws,'WSAGetLastError',c.c_int)
    invalid=c.c_size_t(-1).value
    start=proc(image,PREFIX+'start',U,P,U)
    acquire,release,close=[proc(image,PREFIX+n,U,P) for n in ('acquire','release','close')]
    pools=[c.addressof(c.c_byte.in_dll(image,'net_platform_pool'+str(i))) for i in range(2)]
    def snapshot(pool):
        return dict(zip(('state','users','owned_WSA','preferIPv4Stack','IPv4','IPv6','reuseport','reserved',
                         'startup_calls','cleanup_calls','probe_socket','probe_pending','reserved76'),
                        (*[U.from_address(pool+i).value for i in range(16,48,4)],
                         Q.from_address(pool+48).value,Q.from_address(pool+56).value,Q.from_address(pool+64).value,
                         U.from_address(pool+72).value,U.from_address(pool+76).value)))
    def live_socket(family=2):
        value=sock(family,1,0)
        S.check(value!=invalid,'Loaded platform owner did not retain working Winsock: '+str(last()))
        S.check(close_socket(value)==0,'Real socket cleanup failed')
    # Neither Python fixtures nor the test initialize Winsock on this process.
    before=sock(2,1,0)
    inherited=before!=invalid
    if inherited:
        S.check(close_socket(before)==0,'Inherited Winsock socket cleanup failed')
    else:
        S.check(last()==10093,'Unexpected initial socket failure')
    pool,other=pools
    cold=snapshot(pool)
    S.check(all(v==0 for v in cold.values()) and acquire(pool)==21 and release(pool)==87 and close(pool)==0,
            'Cold owner boundary differs')
    S.check(start(pool,2)==87 and start(None,0)==87 and acquire(None)==87 and close(None)==87 and
            snapshot(pool)==cold,'Invalid platform input acquired resources')
    barrier=Barrier(8,timeout=15)
    def initialize(_):
        barrier.wait()
        S.check(start(pool,0)==0,'Concurrent owner start failed')
        return get_native_id()
    with ThreadPoolExecutor(8) as workers:
        owners=list(workers.map(initialize,range(8)))
    opened=snapshot(pool)
    S.check(len(set(owners))==8 and opened['state']==opened['owned_WSA']==1 and
            opened['startup_calls']==1 and opened['cleanup_calls']==0 and opened['reuseport']==0,
            'Concurrent start acquired more than one Winsock reference')
    live_socket()
    ipv6=sock(23,1,0)
    observed_v6=ipv6!=invalid
    if observed_v6:
        S.check(close_socket(ipv6)==0,'IPv6 oracle socket cleanup failed')
    S.check(opened['IPv4']==1 and opened['IPv6']==observed_v6,'Published IP capabilities differ from actual sockets')
    S.check(start(pool,1)==183 and snapshot(pool)==opened,'Live owner silently changed the Java preference value')
    enter,leave=Barrier(9,timeout=15),Barrier(9,timeout=15)
    def use(_):
        S.check(acquire(pool)==0,'Owner lease failed')
        try:
            live_socket()
            enter.wait()
            leave.wait()
            live_socket()
            return get_native_id()
        finally:
            S.check(release(pool)==0,'Owner lease release failed')
    with ThreadPoolExecutor(8) as workers:
        active=[workers.submit(use,i) for i in range(8)]
        try:
            enter.wait()
            S.check(snapshot(pool)['users']==8 and close(pool)==170 and snapshot(pool)['owned_WSA']==1,
                    'Owner closed Winsock while eight real OS threads held leases')
            live_socket()
        finally:
            leave.wait()
        users=[f.result(timeout=15) for f in active]
    S.check(len(set(users))==8 and snapshot(pool)['users']==0 and release(pool)==87,
            'OS-thread lease accounting or underflow boundary failed')
    S.check(start(other,1)==0 and snapshot(other)['IPv6']==0 and snapshot(other)['preferIPv4Stack']==1,
            'True preference did not restrict the second owner IPv6 capability')
    S.check(close(pool)==0,'First owner close failed')
    live_socket()
    S.check(close(other)==0 and close(other)==0,'Second owner close or idempotent close failed')
    for i in range(16):
        S.check(start(pool,i&1)==0 and acquire(pool)==0,'Repeated owned lifetime failed to open')
        live_socket()
        S.check(release(pool)==0 and close(pool)==0,'Repeated owned lifetime failed to close')
    final=[snapshot(p) for p in pools]
    S.check(all(v['state']==v['users']==v['owned_WSA']==0 and v['startup_calls']==v['cleanup_calls'] for v in final),
            'Final platform resource ownership is unbalanced')
    after=sock(2,1,0)
    if inherited:
        S.check(after!=invalid and close_socket(after)==0,'The owner consumed another component Winsock reference')
    else:
        S.check(after==invalid and last()==10093,'Owner leaked a Winsock reference after final close')
    return dict(source_MASM_platform_lifetime_verified=True,concurrent_start_OS_threads=len(set(owners)),
        concurrent_socket_lease_OS_threads=len(set(users)),close_while_leased_status=170,
        actual_socket_calls_succeeded_after_start=True,independent_owner_survived_peer_close=True,
        before_external_Winsock_reference=inherited,IPv4=bool(opened['IPv4']),IPv6=bool(opened['IPv6']),
        preferences_checked=[False,True],repeated_lifetimes=16,final_owners=final,
        Java_property_source_read=False,JNI_OnLoad_implemented=False,NativeLibraries_load_completed=False,game_started=False)


def execute_faults(dll):
    image=c.CDLL(str(dll))
    ws=c.WinDLL('ws2_32.dll')
    sock=proc(ws,'socket',c.c_size_t,c.c_int,c.c_int,c.c_int)
    close_socket=proc(ws,'closesocket',c.c_int,c.c_size_t)
    get_option=proc(ws,'getsockopt',c.c_int,c.c_size_t,c.c_int,c.c_int,P,P)
    last=proc(ws,'WSAGetLastError',c.c_int)
    invalid=c.c_size_t(-1).value
    start=proc(image,PREFIX+'start',U,P,U)
    acquire,close=[proc(image,PREFIX+n,U,P) for n in ('acquire','close')]
    addresses=lambda n:c.addressof(c.c_byte.in_dll(image,n))
    pool,peer=[addresses('net_platform_pool'+str(i)) for i in range(2)]
    field=lambda offset:U.from_address(pool+offset).value
    count=lambda offset:Q.from_address(pool+offset).value
    stat=lambda name:Q.from_address(addresses('fault_'+name)).value
    def working_socket():
        value=sock(2,1,0)
        S.check(value!=invalid and close_socket(value)==0,'Peer owner lost working Winsock after a failed close')
    def socket_type(handle,alive):
        value,size=c.c_int(),c.c_int(4)
        status=get_option(handle,0xffff,0x1008,c.byref(value),c.byref(size))
        if alive:
            S.check(status==0 and value.value==1,'Failed probe handle was not retained as a real stream socket')
        else:
            S.check(status==-1 and last()==10038,'Recovered probe handle still names an open socket')
    S.check(start(peer,0)==0,'Fault-test peer did not acquire its independent Winsock reference')
    working_socket()
    cleanup_before=stat('cleanup_attempts')
    U.from_address(addresses('fault_close_remaining')).value=2
    U.from_address(addresses('fault_cleanup_remaining')).value=1
    S.check(start(pool,0)==10035 and field(16)==2 and field(24)==1 and field(20)==0 and
            field(72)==1 and count(48)==1 and count(56)==0 and stat('cleanup_attempts')==cleanup_before,
            'Failed probe was published ready or cleaned up with its socket still open')
    pending=count(64)
    socket_type(pending,True)
    S.check(start(pool,0)==21 and start(pool,1)==21 and acquire(pool)==21,
            'Failed-owned initialization was reused as ready')
    S.check(close(pool)==10035 and field(16)==2 and field(72)==1 and count(64)==pending and
            stat('cleanup_attempts')==cleanup_before,'Failed socket retry lost ownership or prematurely ran WSACleanup')
    socket_type(pending,True)
    working_socket()
    S.check(close(pool)==10050 and field(16)==2 and field(24)==1 and field(72)==0 and count(64)==0 and
            count(56)==0 and stat('cleanup_attempts')==cleanup_before+1,
            'Failed cleanup was published ready or discarded the owned Winsock reference')
    socket_type(pending,False)
    S.check(start(pool,0)==21 and acquire(pool)==21,'Failed cleanup permitted a start or lease')
    working_socket()
    S.check(close(pool)==0 and field(16)==field(24)==field(72)==0 and count(48)==count(56)==1,
            'Retry did not close and balance the failed-owned lifetime')
    working_socket()
    S.check(close(peer)==0 and close(pool)==0 and stat('socket_creations')==stat('socket_closes'),
            'Fault recovery leaked a probe or consumed the independent peer reference')
    value=sock(2,1,0)
    S.check(value==invalid and last()==10093,'Fault recovery leaked a process-local Winsock reference')
    return dict(failed_probe_close_status=10035,failed_cleanup_status=10050,failed_owned_state=2,
        start_and_acquire_rejected_until_close=True,unclosed_probe_SOCKET_retained_and_retried=True,
        WSACleanup_skipped_until_probe_closed=True,independent_owner_stayed_usable=True,
        actual_probe_sockets_created=stat('socket_creations'),actual_probe_sockets_closed=stat('socket_closes'),
        final_socket_error=10093,production_imports_rebound=False,test_DLL_imports_rebound=True,
        JNI_OnLoad_implemented=False,NativeLibraries_load_completed=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ART/'builtin-net-platform-tests'/uuid4().hex)
    args=parser.parse_args()
    dll=build(args.output)
    result=execute(dll)
    faults=build(args.output/'faults',faults=True)
    result['failure_ownership_recovery']=execute_faults(faults)
    result['failure_image_receipt']=S.artifact(args.output/'faults/image.json')
    result['image_receipt']=S.artifact(args.output/'image.json')
    S.write(args.output/'result.json',result)
    print(args.output/'result.json')
