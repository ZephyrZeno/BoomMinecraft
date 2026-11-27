"""Compare the bounded ASM invoke0 component with an isolated locked JDK.

The Java source below is an oracle fixture only. Its throwing target is not
part of the translated image; the ASM exception test calls the original cold
VM.getSavedProperties body. Neither case certifies the default Method API.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('invoke_oracle_component',ROOT/'scripts/test-method-invoke.py')
T=importlib.util.module_from_spec(spec);spec.loader.exec_module(T)
S=T.S
JAVA_SOURCE=r'''import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
class MethodInvokeOracle {
 static Object invoke(Method n,Method t,Object receiver,Object[] args)throws Throwable {
  try {return n.invoke(null,new Object[]{t,receiver,args});}
  catch(InvocationTargetException x) {throw x.getCause();}
 }
 static String describe(Object x) {
  if(x==null)return "NULL";
  if(x instanceof Object[] a) {
   StringJoiner j=new StringJoiner(",");for(Object v:a)j.add(((Enum<?>)v).name());return "ARRAY:"+j;
  }
  return x.getClass().getName();
 }
 // Oracle-only target. The ASM component uses original VM Java Code instead.
 static Object explode() {throw new IllegalStateException("Not yet initialized");}
 public static void main(String[] args)throws Throwable {
  if(System.getProperty("jdk.reflect.useDirectMethodHandle")!=null ||
     System.getProperty("jdk.reflect.useNativeAccessorOnly")!=null)throw new AssertionError("override");
  List<String> out=new ArrayList<>();
  for(String implementation:new String[]{"jdk.internal.reflect.DirectMethodHandleAccessor$NativeAccessor",
                                         "jdk.internal.reflect.NativeMethodAccessorImpl"}) {
   Method n=Class.forName(implementation).getDeclaredMethod("invoke0",Method.class,Object.class,Object[].class);
   n.setAccessible(true);
   for(String[] spec:new String[][]{{"java.util.Optional","empty"},{"java.util.Collections","emptyList"},
                                     {"java.lang.System","getSecurityManager"},{"java.lang.StackWalker$Option","values"}}) {
    Method target=Class.forName(spec[0],false,null).getDeclaredMethod(spec[1]);
    Object value=invoke(n,target,new Object(),null);
    out.add("RESULT\t"+implementation+"\t"+spec[0]+"\t"+spec[1]+"\t"+describe(value));
    if(!describe(value).equals(describe(invoke(n,target,null,new Object[0]))))throw new AssertionError("empty/static");
    try {invoke(n,target,null,new Object[1]);throw new AssertionError("arity");}
    catch(IllegalArgumentException x) {out.add("ARITY\t"+implementation+"\t"+x.getMessage());}
   }
   Method target=MethodInvokeOracle.class.getDeclaredMethod("explode");
   try {invoke(n,target,null,null);throw new AssertionError("target");}
   catch(InvocationTargetException x) {
    if(!(x.getCause() instanceof IllegalStateException)||x.getCause()!=x.getTargetException())throw x;
    out.add("ITE\t"+implementation+"\t"+x.getCause().getClass().getName()+"\t"+x.getCause().getMessage());
   }
  }
  Files.writeString(Path.of(args[0]),String.join("\n",out));
 }
}
'''


def run(execution_file,java_home,output):
    execution=S.read(execution_file);images_file=S.checked(execution['images']);images=S.read(images_file)
    S.check(execution['verified'] and execution['target_Throwable_ITE_wrapping_verified'] and
        len(execution['direct_source_Method_cases'])==4 and len(execution['quiescent_collections'])==4 and
        len(execution['concurrent_OS_calls'])==8,'A complete passing ASM bounded component is required')
    S.check(images['execution_tool']==S.artifact(ROOT/'scripts/test-method-invoke.py'),
        'The executed ASM component harness has changed')
    for row in images['inputs']+images['original_inputs']:T.N.D.checked(row)
    for name in ('candidate','candidate_proof','current_Method_candidate','current_Method_proof','source_manifest','source_proof'):
        S.checked(images[name])
    java_home=java_home.resolve();release=java_home/'release'
    producer=S.read(S.checked(images['methods_images']));catalog=producer['oracle_modules']
    modules=java_home/'lib/modules';catalog_digest=dict(size=modules.stat().st_size)
    for algorithm in ('sha1','sha256'):
        with modules.open('rb') as stream:catalog_digest[algorithm]=hashlib.file_digest(stream,algorithm).hexdigest()
    S.check(modules.resolve()==Path(catalog['path']).resolve() and catalog_digest==catalog['digest'] and
        'JAVA_VERSION="21.' in release.read_text(),'The complete locked input-catalog JDK image is required')
    files=[java_home/name for name in ('bin/java.exe','bin/java.dll','bin/server/jvm.dll','lib/modules','lib/src.zip','release')]
    before=[S.artifact(file) for file in files]
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated oracle output required')
    output.mkdir(parents=True);source=output/'MethodInvokeOracle.java';source.write_text(JAVA_SOURCE)
    protocol=output/'protocol.txt';command=[str(java_home/'bin/java.exe'),'--add-opens',
        'java.base/jdk.internal.reflect=ALL-UNNAMED',str(source),str(protocol)]
    with (output/'stdout.txt').open('wb') as stdout,(output/'stderr.txt').open('wb') as stderr:
        completed=subprocess.run(command,cwd=output,stdout=stdout,stderr=stderr,timeout=90)
    S.check(completed.returncode==0,'Isolated JDK private-native oracle failed')
    S.check(before==[S.artifact(file) for file in files],'Locked JDK oracle bytes changed')
    actual=[];arity=[];exceptions=[]
    for line in protocol.read_text().splitlines():
        parts=line.split('\t');kind=parts[0]
        if kind=='RESULT':actual.append(dict(implementation=parts[1],owner=parts[2],name=parts[3],normalized=parts[4]))
        elif kind=='ARITY':arity.append(dict(implementation=parts[1],message=parts[2]))
        elif kind=='ITE':exceptions.append(dict(implementation=parts[1],cause_type=parts[2],message=parts[3]))
        else:raise ValueError('Unknown JDK oracle protocol row')
    implementations=[owner.replace('/','.') for owner,_ in T.B.C.SPECS];expected=[]
    for case in execution['direct_source_Method_cases']:
        for result in case['natives']:
            S.check(not result['context'][0] and not result['context'][3],'ASM native returned a pending error/source frame')
            if case['descriptor'][2:].startswith('['):
                S.check(result['normal_runtime_type']==case['descriptor'][2:],'ASM original array clone lost its actual normal array type')
            expected.append(dict(implementation=implementations[result['native_operation']],owner=case['owner'].replace('/','.'),
                name=case['name'],normalized=result['normalized']))
    key=lambda row:(row['implementation'],row['owner'],row['name'])
    S.check(len(actual)==8 and sorted(actual,key=key)==sorted(expected,key=key),'Actual ASM/JDK noarg static reference returns differ')
    S.check(len(arity)==8 and all(row['message']==execution['wrong_arity']['message']=='wrong number of arguments' for row in arity),
        'ASM/JDK original wrong-arity constructor protocol differs')
    expected_exceptions=[dict(implementation=implementations[row['native_operation']],cause_type=row['cause_runtime_type'].replace('/','.'),
        message=row['message']) for row in execution['target_exceptions']]
    S.check(exceptions==expected_exceptions,'ASM original-cold-VM/JDK fixture InvocationTargetException cause protocol differs')
    result=dict(schema=1,verified=True,scope='bounded_two_original_invoke0_ASM_component_and_isolated_JDK_reference',
        execution=S.artifact(execution_file),images=S.artifact(images_file),tool=S.artifact(Path(__file__)),
        Java_oracle=dict(command=command,inputs=before,source=S.artifact(source),protocol=S.artifact(protocol),
            default_reflection_properties_overridden=False,oracle_only=True),
        direct_return_comparisons=actual,actual_return_comparisons=8,empty_arguments_and_static_receiver_ignored=True,
        JDK_wrong_arity_observations=arity,ASM_wrong_arity_observations=1,target_exception_comparisons=exceptions,
        ASM_throwing_target='original_cold_VM_getSavedProperties',JDK_throwing_target='isolated_oracle_fixture_only',
        normal_Method_objects_and_original_target_Java=True,OS_threads=8,concurrent_native_calls=512,
        quiescent_collections=4,default_original_Java_API=execution['default_original_Java_API'],
        historical_full_selection_reused=images['historical_full_selection_reused'],
        current_full_selection_reverified=images['current_full_selection_reverified'],
        additional_stop_table_in_original_full_selection=False,additional_stop_controller_auto_admission=False,
        current_shared_namespace_accepted=False,shared_registered=False,game_started=False)
    path=output/'result.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execution',type=Path,required=True)
    parser.add_argument('--java-home',type=Path,default=Path('D:/Dev/Java/jdk-21'))
    parser.add_argument('--output',type=Path,default=S.ART/'method-invoke'/('oracle-'+uuid4().hex))
    args=parser.parse_args();print(run(args.execution.resolve(),args.java_home,args.output))
