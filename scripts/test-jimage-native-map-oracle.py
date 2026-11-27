"""Original JDK lookup-cache/DirectByteBuffer oracle, isolated in project .boom."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('jimage_oracle_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
S=module('runtime-provider-source')
HOME=Path('D:/Dev/Java/jdk-21')
JAVA=r'''import java.lang.reflect.*;
import java.nio.*;
import java.nio.file.*;
import java.util.*;
public class NativeMapOracle {
  static Method get;
  static ByteBuffer map(String name) throws Exception { return (ByteBuffer)get.invoke(null,name); }
  static String hex(byte[] bytes) { return HexFormat.of().formatHex(bytes); }
  static void row(String id, ByteBuffer b) {
    if (b==null) { System.out.println(id+"\tNULL"); return; }
    byte[] header=new byte[28]; b.duplicate().get(header);
    System.out.println(id+"\tMAP\t"+b.capacity()+"\t"+b.position()+"\t"+b.limit()+"\t"+
      b.isDirect()+"\t"+b.hasArray()+"\t"+b.isReadOnly()+"\t"+b.order()+"\t"+b.getInt(0)+"\t"+hex(header));
  }
  public static void main(String[] args) throws Exception {
    Class<?> owner=Class.forName("jdk.internal.jimage.NativeImageBuffer");
    get=owner.getDeclaredMethod("getNativeMap",String.class);get.setAccessible(true);
    String modules=Path.of(System.getProperty("java.home"),"lib","modules").toString();
    ByteBuffer first=map(modules),second=map(modules);
    row("vm_cached_modules",first);row("repeat",second);
    System.out.println("distinct_wrappers\t"+(first!=second));
    Field address=Buffer.class.getDeclaredField("address");address.setAccessible(true);
    System.out.println("same_actual_view\t"+(address.getLong(first)==address.getLong(second)));
    Path fixture=Path.of(args[0]);Files.write(fixture,new byte[]{1,2,3,4});
    row("exists_but_not_VM_cached",map(fixture.toString()));
    row("missing",map(fixture+".missing"));row("empty",map(""));
    row("embedded_NUL",map(modules+"\u0000suffix"));
    row("case_changed",map(modules.toUpperCase(Locale.ROOT)));
    row("dot_component",map(modules.substring(0,modules.lastIndexOf('\\')+1)+".\\modules"));
    row("forward_slashes",map(modules.replace('\\','/')));
    row("over_owner_key_budget",map("x".repeat(32768)));
    row("unpaired_surrogate",map("\ud800"));
  }
}'''


def run(output,execution=None):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated JDK oracle required')
    output.mkdir(parents=True)
    modules=HOME/'lib/modules';release=HOME/'release'
    pinned=dict(size=141325186,sha256='541b62fa469595c7eeb2c329dad24151887be50056e08b5e4e1534c6260bb263')
    S.check(S.digest(modules)==pinned,'Original locked JDK modules changed')
    S.check('JAVA_VERSION="21.0.13"' in release.read_text(encoding='utf-8') or
        'JAVA_VERSION="21.0.13.0.3"' in release.read_text(encoding='utf-8'),'Locked JDK21 oracle release differs')
    source=output/'NativeMapOracle.java';source.write_text(JAVA,encoding='utf-8')
    java,javac=HOME/'bin/java.exe',HOME/'bin/javac.exe'
    before={str(path):S.artifact(path) for path in (source,java,javac,modules,release,Path(__file__))}
    with (output/'javac.log').open('xb') as log:
        subprocess.run([javac,'-d',output,source],cwd=output,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    command=[java,'--add-opens','java.base/jdk.internal.jimage=ALL-UNNAMED','--add-opens','java.base/java.nio=ALL-UNNAMED',
        '-cp',output,'NativeMapOracle',output/'uncached.bin']
    with (output/'oracle.txt').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
        subprocess.run(command,cwd=output,stdout=stdout,stderr=stderr,check=True,timeout=120)
    rows={}
    for line in (output/'oracle.txt').read_text(encoding='utf-8').splitlines():
        key,*values=line.split('\t');S.check(key not in rows,'Duplicate original JDK oracle case');rows[key]=values
    expected={'vm_cached_modules','repeat','distinct_wrappers','same_actual_view','exists_but_not_VM_cached','missing',
        'empty','embedded_NUL','case_changed','dot_component','forward_slashes','over_owner_key_budget','unpaired_surrogate'}
    S.check(set(rows)==expected and rows['distinct_wrappers']==['true'] and rows['same_actual_view']==['true'],
        'Original JDK did not create distinct wrappers over its same actual held mapping')
    for key in expected-{'vm_cached_modules','repeat','distinct_wrappers','same_actual_view'}:
        S.check(rows[key]==['NULL'],'Original JDK lookup unexpectedly opened/normalized a path: '+key)
    hit=rows['vm_cached_modules'];S.check(hit==rows['repeat'] and hit[:9]==['MAP',str(pinned['size']),'0',str(pinned['size']),
        'true','false','false','BIG_ENDIAN',str(int.from_bytes(modules.read_bytes()[:4],'big',signed=True))],
        'Original JNI buffer capacity/flags/order/primitive read differs')
    component=None
    if execution is not None:
        result=S.read(execution);S.check(result['verified'],'Actual assembly source component must pass before oracle comparison')
        shape=result['lookup_hits'][0]['shape']
        S.check((shape['capacity'],shape['position'],shape['limit'],shape['att'],shape['cleaner'])==(pinned['size'],0,pinned['size'],0,0) and
            result['lookup_hits'][0]['first_28_bytes']==hit[9],
            'Actual original Java constructor shape/header differs from the original JNI oracle')
        if result['read_primitive_boundary']['passed']:
            import ctypes
            S.check(ctypes.c_int32(result['read_primitive_boundary']['value']).value==int(hit[8]),'Actual original mapped getInt differs')
        component=S.artifact(execution)
    for path,record in before.items():S.check(S.artifact(path)==record,'Oracle sealed input changed')
    result=dict(schema=1,verified=True,scope='original_JDK_NativeImageBuffer_lookup_and_real_JNI_JJ_buffer_oracle',
        cases=rows,component_execution=component,inputs=list(before.values()),
        original_JVM_held_SDK_mapping_compared_to_explicit_ASM_owned_fixture_mapping=True,
        identical_registry_population_not_claimed=True,lookup_never_opens_the_uncached_fixture=True,
        production_JVM_fallback=False,production_JDK_C_DLL_used=False,game_started=False)
    path=output/'result.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execution',type=Path);args=parser.parse_args();print(run(args.output,args.execution))
