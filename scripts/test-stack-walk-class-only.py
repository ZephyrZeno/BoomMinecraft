"""Independent Class-only StackWalker components and a console-only JDK oracle."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('stack_walk_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


B=module('stack-walk-candidate');S=B.S


def oracle(output):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART/'stack-walk') and not output.exists(),'Fresh isolated JDK oracle output required')
    output.mkdir(parents=True);home=Path('D:/Dev/Java/jdk-21')
    tools=[S.artifact(home/name) for name in ('bin/java.exe','bin/javac.exe','bin/server/jvm.dll','lib/modules','lib/src.zip')]
    source=output/'StackWalkDebugOracle.java'
    source.write_text('''import java.awt.Graphics;
import javax.swing.DebugGraphics;
import java.util.concurrent.*;
import java.util.*;
public class StackWalkDebugOracle {
 static void one(){DebugGraphics graphics=new DebugGraphics((Graphics)null);
   if(graphics.getClass()!=DebugGraphics.class)throw new AssertionError();}
 public static void main(String[] argv)throws Exception{
   one();CyclicBarrier gate=new CyclicBarrier(8);ExecutorService executor=Executors.newFixedThreadPool(8);
   List<Future<Integer>> answers=new ArrayList<>();
   try{for(int i=0;i<8;i++)answers.add(executor.submit(()->{gate.await();for(int n=0;n<128;n++)one();return 128;}));
     int count=1;for(Future<Integer> answer:answers)count+=answer.get();
     System.out.println("original_DebugGraphics_Graphics_constructor="+count);
   }finally{executor.shutdown();}
 }
}
''',encoding='utf-8')
    compile_result=subprocess.run([str(home/'bin/javac.exe'),'-d',str(output),str(source)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (output/'javac.stdout').write_bytes(compile_result.stdout);(output/'javac.stderr').write_bytes(compile_result.stderr)
    S.check(compile_result.returncode==0,'JDK oracle compilation failed')
    compiled=S.artifact(output/'StackWalkDebugOracle.class')
    command=[str(home/'bin/java.exe'),'-Xlog:class+init=info:file=class-init.log','-cp',str(output),'StackWalkDebugOracle']
    process=subprocess.run(command,cwd=output,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (output/'stdout.txt').write_bytes(process.stdout);(output/'stderr.txt').write_bytes(process.stderr)
    S.check(process.returncode==0 and process.stdout.decode().strip()=='original_DebugGraphics_Graphics_constructor=1025','Original JDK StackWalker oracle failed')
    log=(output/'class-init.log').read_text(encoding='utf-8')
    S.check("Initializing 'javax/swing/DebugGraphics'" in log and "Initializing 'java/awt/image/BufferedImage'" not in log,
            'JDK oracle did not retain the no-BufferedImage original branch')
    result=dict(verified=True,scope='JDK_reference_only_original_DebugGraphics_cold_and_8_OS_no_desktop_branch',
        original_constructor_calls=1025,OS_workers=8,iterations_per_worker=128,BufferedImage_initialized=False,
        headless_property_override=False,desktop_automation=False,game_runtime=False,jvm_fallback=False,
        command=command,tools=tools,compiled_class=compiled,execution_tool=S.artifact(Path(__file__)),
        source=S.artifact(source),stdout=S.artifact(output/'stdout.txt'),stderr=S.artifact(output/'stderr.txt'),class_init_log=S.artifact(output/'class-init.log'))
    S.check(all(S.artifact(record['path'])==record for record in tools+[compiled]),'Oracle tool/image/input changed during execution')
    S.write(output/'verification.json',result);return output/'verification.json'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--oracle',type=Path);args=parser.parse_args()
    S.check(args.oracle is not None,'Specify an isolated --oracle output')
    print(oracle(args.oracle))
