"""Development JDK oracle for the same generated hidden Consumer classfile."""
import argparse
import importlib.util
from pathlib import Path
import subprocess


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_lambda_oracle_source',ROOT/'scripts/normal-lambda-source.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
S=C.S
JAVA=r'''
import java.lang.invoke.MethodHandles;
import java.lang.module.ModuleDescriptor;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import java.util.function.Consumer;
public class NormalLambdaOracle {
 interface Action {void run() throws Throwable;}
 static void test(String key,Action body) {
  try {body.run();System.out.println("CASE|"+key+"|OK");}
  catch(Throwable error) {while(error instanceof InvocationTargetException)error=((InvocationTargetException)error).getCause();
   System.out.println("CASE|"+key+"|"+error.getClass().getName());}
 }
 public static void main(String[] args) throws Throwable {
  Field field=MethodHandles.Lookup.class.getDeclaredField("IMPL_LOOKUP");field.setAccessible(true);
  MethodHandles.Lookup trusted=(MethodHandles.Lookup)field.get(null);Class<?> host=Class.forName(args[1]);
  Class<?> type=trusted.in(host).defineHiddenClass(Files.readAllBytes(Path.of(args[0])),true,
    MethodHandles.Lookup.ClassOption.NESTMATE).lookupClass();
  Method factory=type.getDeclaredMethod("$capture");factory.setAccessible(true);
  @SuppressWarnings("unchecked") Consumer<Object> consumer=(Consumer<Object>)factory.invoke(null);
  if(!type.isHidden() || type.getModule()!=host.getModule() || type.getClassLoader()!=host.getClassLoader() ||
     !type.getName().startsWith(args[2]+"/0x") || consumer.getClass()!=type || consumer==factory.invoke(null))
    throw new AssertionError("hidden class/fresh factory/module/loader identity");
  System.out.println("HIDDEN|"+type.getName());
  test("SAM-valid",()->consumer.accept("java.lang"));
  test("SAM-unicode",()->consumer.accept("\u03bb.valid"));
  test("SAM-wrong-class",()->consumer.accept(new Object()));
  test("SAM-null",()->consumer.accept(null));
  test("SAM-null-receiver",()->((Consumer<Object>)null).accept("java.lang"));
  test("SAM-invalid",()->consumer.accept("bad-name"));
  test("strict-Builder",()->{var builder=ModuleDescriptor.newModule("lambda.witness");
   if(builder.packages(Set.of("lambda.valid","java.lang"))!=builder || builder.build()==null)
    throw new AssertionError("strict Builder did not complete");});
 }
}
'''


def run(images_file,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated lambda oracle output required')
    images=S.read(images_file);manifest=S.read(S.checked(images['expansion']));[generated]=manifest['generated']
    home=Path(images['oracle_home']);java=home/'bin/java.exe';javac=home/'bin/javac.exe'
    modules=images['oracle_modules'];actual=S.digest(modules['path'])
    S.check(all(actual[k]==modules['digest'][k] for k in ('size','sha256')),'Pinned oracle JDK modules changed')
    output.mkdir(parents=True);source=output/'NormalLambdaOracle.java';source.write_text(JAVA)
    with (output/'compile.log').open('wb') as log:
        subprocess.run([javac,'-d',output,source],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
    arguments=[java,'--add-opens=java.base/java.lang.invoke=ALL-UNNAMED','--add-opens=java.base/java.lang.module=ALL-UNNAMED',
        '-cp',output,'NormalLambdaOracle',S.checked(generated['class_file']),
        generated['contract']['host']['name'].replace('/','.'),generated['origin']['binary_name']]
    result=subprocess.run(arguments,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False,timeout=90)
    (output/'oracle.log').write_bytes(result.stdout);lines=result.stdout.decode().splitlines()
    S.check(result.returncode==0,'Generated classfile JDK reference failed; preserved oracle.log')
    cases={parts[1]:parts[2] for line in lines if (parts:=line.split('|'))[0]=='CASE'}
    expected={'SAM-valid':'OK','SAM-unicode':'OK','SAM-wrong-class':'java.lang.ClassCastException','SAM-null':'java.lang.IllegalArgumentException',
        'SAM-null-receiver':'java.lang.NullPointerException',
        'SAM-invalid':'java.lang.IllegalArgumentException','strict-Builder':'OK'}
    S.check(cases==expected and len([line for line in lines if line.startswith('HIDDEN|')])==1,'Original generated classfile JDK oracle differs')
    native_file=images_file.parent/'execution.json';native=S.read(native_file);S.check(native['verified'],'Actual ASM witness required alongside JDK reference')
    negatives=native['semantic_negative_cases']
    S.check(negatives['wrong_class_context'][0]==12 and negatives['null_receiver_context'][0]==4 and
        negatives['null_argument_original_exception']==cases['SAM-null'] and
        negatives['void_discarded_original_nonnull_reference'] and native['strict_source_witness']['descriptor_built'],
        'ASM normal Context32 projection differs from the development JDK')
    proof=dict(schema=1,verified=True,scope='development_JDK_generated_hidden_class_and_original_Builder_comparison',
        images=S.artifact(images_file),actual_ASM_execution=S.artifact(native_file),generated_classfile=generated['class_file'],
        java=S.artifact(java),javac=S.artifact(javac),modules=modules,source=S.artifact(source),tool=S.artifact(Path(__file__)),
        oracle_log=S.artifact(output/'oracle.log'),cases=cases,wrong_class_and_NPE_normal_Context32_projection_agree=True,
        same_generated_classfile_defined_hidden_as_original_lookup_host=True,original_Java_fields_patched=False,
        oracle_is_game_runtime=False,all_source_matched_sites_executed=False,game_started=False)
    file=output/'verification.json';S.write(file,proof);return file


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--images',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(run(args.images.resolve(),args.output))
