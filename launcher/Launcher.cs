// Build/launch UI only. No gameplay or game-side scheduling executes here.
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Web.Script.Serialization;

sealed class BoomChild : IDisposable {
    public readonly ConcurrentQueue<string> Lines = new ConcurrentQueue<string>();
    public Process Process;
    static string Quote(string text) {
        var result=new StringBuilder("\""); int slashes=0;
        foreach(char c in text) {
            if(c=='\\') { slashes++; continue; }
            if(c=='"') result.Append('\\',slashes*2+1).Append(c);
            else result.Append('\\',slashes).Append(c);
            slashes=0;
        }
        return result.Append('\\',slashes*2).Append('"').ToString();
    }
    public void Start(string executable,string root,string[] args) {
        var info=new ProcessStartInfo(executable);
        var parts=new string[args.Length]; for(int i=0;i<args.Length;i++) parts[i]=Quote(args[i]);
        info.Arguments=String.Join(" ",parts); info.WorkingDirectory=root;
        info.UseShellExecute=false; info.CreateNoWindow=true;
        info.RedirectStandardOutput=true; info.RedirectStandardError=true; info.RedirectStandardInput=true;
        info.StandardOutputEncoding=Encoding.UTF8; info.StandardErrorEncoding=Encoding.UTF8;
        Process=new Process(); Process.StartInfo=info;
        Process.OutputDataReceived+=(s,e)=>{ if(e.Data!=null) Lines.Enqueue(e.Data); };
        Process.ErrorDataReceived+=(s,e)=>{ if(e.Data!=null) Lines.Enqueue(e.Data); };
        if(!Process.Start()) throw new Exception("Could not start backend");
        Process.BeginOutputReadLine(); Process.BeginErrorReadLine();
    }
    public void Stop() {
        if(Process!=null && !Process.HasExited) {
            try { Process.StandardInput.WriteLine("stop"); Process.StandardInput.Flush(); } catch(IOException) {} catch(InvalidOperationException) {}
        }
    }
    public void ForceStop() {
        if(Process!=null && !Process.HasExited) {
            // Only this launcher's still-running child tree is targeted.
            var stop=new ProcessStartInfo("taskkill.exe","/PID "+Process.Id+" /T /F");
            stop.UseShellExecute=false; stop.CreateNoWindow=true;
            using(var killer=System.Diagnostics.Process.Start(stop)) { killer.WaitForExit(5000); }
        }
    }
    public void Dispose() { if(Process!=null) Process.Dispose(); }
}

sealed class LauncherForm : Form {
    readonly string root, backend;
    readonly List<Button> taskButtons=new List<Button>();
    readonly NumericUpDown memory=new NumericUpDown();
    readonly TextBox session=new TextBox(), gameDirectory=new TextBox(), log=new TextBox();
    readonly Label status=new Label();
    readonly Button stop=new Button();
    readonly Timer timer=new Timer();
    BoomChild child;
    DateTime? stopDeadline;
    bool closing;
    string logFile;

    public LauncherForm(string workspace,string executable) {
        root=workspace; backend=executable;
        Text="BoomMinecraft 1.21.1 Launcher";
        Size=new Size(1040,780); MinimumSize=new Size(920,700); StartPosition=FormStartPosition.CenterScreen;
        Font=new Font("Microsoft YaHei UI",10); AutoScaleMode=AutoScaleMode.Dpi;
        var layout=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(18),ColumnCount=1,RowCount=7};
        foreach(int height in new[]{44,64,42,42,52}) layout.RowStyles.Add(new RowStyle(SizeType.Absolute,height));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent,100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute,34));
        layout.Controls.Add(new Label {Text="BoomMinecraft  |  Java 1.21.1",Font=new Font(Font.FontFamily,18,FontStyle.Bold),Dock=DockStyle.Fill},0,0);
        layout.Controls.Add(new Label {Text="Minecraft Java 版 1.21.1\r\n开发构建：当前版本尚不能启动完整游戏。",Dock=DockStyle.Fill},0,1);
        var settings=new FlowLayoutPanel {Dock=DockStyle.Fill};
        settings.Controls.Add(new Label {Text="内存上限 (MiB)：",AutoSize=true});
        memory.Minimum=512; memory.Maximum=32768; memory.Increment=512; memory.Value=4096; memory.Width=85;
        settings.Controls.Add(memory);
        settings.Controls.Add(new Label {Text="   游戏目录：",AutoSize=true});
        gameDirectory.Text=Path.Combine(root,".boom","runs","native-client");gameDirectory.Width=550;
        settings.Controls.Add(gameDirectory);layout.Controls.Add(settings,0,2);
        var sessionRow=new FlowLayoutPanel {Dock=DockStyle.Fill};
        sessionRow.Controls.Add(new Label {Text="客户端会话文件：",AutoSize=true}); session.Width=500; sessionRow.Controls.Add(session);
        var browse=new Button {Text="选择文件",AutoSize=true};
        browse.Click+=(s,e)=>{ using(var dialog=new OpenFileDialog {Filter="JSON (*.json)|*.json"}) if(dialog.ShowDialog(this)==DialogResult.OK) session.Text=dialog.FileName; };
        sessionRow.Controls.Add(browse); layout.Controls.Add(sessionRow,0,3);
        var actions=new FlowLayoutPanel {Dock=DockStyle.Fill,WrapContents=true};
        AddAction(actions,"启动游戏",()=>{
            StartTask(backend,Launcher.PlayArguments(gameDirectory.Text,memory.Value,session.Text));
        });
        stop.Text="停止启动"; stop.AutoSize=true; stop.Enabled=false;
        stop.Click+=(s,e)=>BeginStop(); actions.Controls.Add(stop); layout.Controls.Add(actions,0,4);
        log.Multiline=true; log.ReadOnly=true; log.ScrollBars=ScrollBars.Both; log.WordWrap=false; log.Dock=DockStyle.Fill; log.Font=new Font("Consolas",10);
        status.Dock=DockStyle.Fill; status.Text="尚未启动。";
        layout.Controls.Add(log,0,5); layout.Controls.Add(status,0,6); Controls.Add(layout);
        timer.Interval=200; timer.Tick+=(s,e)=>Poll(); timer.Start();
        FormClosing+=(s,e)=>{if(child!=null){e.Cancel=true;closing=true;BeginStop();}};
        FormClosed+=(s,e)=>timer.Dispose();
    }
    void AddAction(FlowLayoutPanel panel,string text,Action action) {
        var button=new Button {Text=text,AutoSize=true,Height=36}; button.Click+=(s,e)=>action(); panel.Controls.Add(button); taskButtons.Add(button);
    }
    void StartTask(string executable,string[] args) {
        if(child!=null)return;
        try {
            if(!File.Exists(executable)) throw new FileNotFoundException("尚未构建此程序，请使用 scripts/build-launcher.py 构建启动器。",executable);
            var directory=Path.Combine(root,".boom","launcher-runs",Guid.NewGuid().ToString("N")); Directory.CreateDirectory(directory); logFile=Path.Combine(directory,"output.log");
            log.Clear(); child=new BoomChild(); child.Start(executable,root,args);
            foreach(var button in taskButtons)button.Enabled=false; memory.Enabled=false; stop.Enabled=true;
            status.Text="正在启动游戏……";
        } catch(Exception error) {
            if(child!=null) {child.Dispose();child=null;}
            log.AppendText(error.Message+Environment.NewLine); status.Text="启动失败";
        }
    }
    void BeginStop() {
        if(child==null)return;
        child.Stop(); if(!stopDeadline.HasValue)stopDeadline=DateTime.UtcNow.AddSeconds(10); stop.Enabled=false;
        status.Text="正在停止；10 秒后结束仍未退出的本次任务。";
    }
    void Drain() {
        string line; var batch=new StringBuilder(); while(child.Lines.TryDequeue(out line))batch.AppendLine(line);
        if(batch.Length==0)return;
        var text=batch.ToString(); File.AppendAllText(logFile,text,new UTF8Encoding(false));
        if(log.TextLength>200000)log.Text=log.Text.Substring(log.TextLength-100000);
        log.AppendText(text);
    }
    void Poll() {
        if(child==null)return;
        try {
            if(stopDeadline.HasValue && DateTime.UtcNow>stopDeadline.Value) {child.ForceStop();stopDeadline=null;}
            Drain();
            if(child.Process.HasExited) {
                child.Process.WaitForExit(); Drain(); status.Text="任务退出，代码 "+child.Process.ExitCode+"。日志："+logFile;
                child.Dispose();child=null;stopDeadline=null;
                foreach(var button in taskButtons)button.Enabled=true; memory.Enabled=true;stop.Enabled=false;
                if(closing)Close();
            }
        } catch(Exception error) {status.Text="任务监控错误："+error.Message;}
    }
}

static class Launcher {
    internal static string[] PlayArguments(string directory,decimal memory,string session) {
        var arguments=new List<string>(new[]{"play","--game-dir",directory,"--memory-mib",memory.ToString(System.Globalization.CultureInfo.InvariantCulture)});
        if(!String.IsNullOrWhiteSpace(session))arguments.AddRange(new[]{"--auth-file",session});
        return arguments.ToArray();
    }
    static int SelfTest(string root,string backend) {
        string directory=Path.Combine(root,".boom","launcher-selftest","game with spaces 测试")+Path.DirectorySeparatorChar;
        var args=new List<string>(PlayArguments(directory,4096,""));args.Add("--dry-run");
        var serializer=new JavaScriptSerializer();
        using(var child=new BoomChild()) {
            child.Start(backend,root,args.ToArray());
            if(!child.Process.WaitForExit(20000)){child.ForceStop();throw new Exception("Headless launch test timed out");}
            child.Process.WaitForExit();string line;var output=new StringBuilder();while(child.Lines.TryDequeue(out line))output.AppendLine(line);
            if(child.Process.ExitCode!=0)throw new Exception(output.ToString());
            var plan=serializer.Deserialize<Dictionary<string,object>>(output.ToString());
            if((string)plan["backend"]!="own-assembly" || (bool)plan["full_game_ready"] || Convert.ToInt32(plan["memory_mib"])!=4096)throw new Exception("Unexpected launch plan");
            if(!String.Equals(((string)plan["game_directory"]).TrimEnd('\\'),directory.TrimEnd('\\'),StringComparison.OrdinalIgnoreCase))throw new Exception("Quoted Unicode game directory was changed");
            if(Directory.Exists(directory))throw new Exception("Dry run created game files");
        }
        var report=serializer.Serialize(new {passed=true,ui_automation_used=false,player_entry="play",compiler_buttons=false,unicode_and_spaces_preserved=true,full_game_ready=false});
        var reportDirectory=Path.Combine(root,".boom","launcher-selftest");Directory.CreateDirectory(reportDirectory);
        File.WriteAllText(Path.Combine(reportDirectory,"result.json"),report,new UTF8Encoding(false));Console.WriteLine(report);return 0;
    }
    [STAThread] static int Main(string[] args) {
        bool selfTest=false;
        try {
            string directory=AppDomain.CurrentDomain.BaseDirectory;
            string root=directory, backend=Path.Combine(directory,"boom.exe");
            var parent=Directory.GetParent(directory.TrimEnd(Path.DirectorySeparatorChar));
            if(parent!=null && File.Exists(Path.Combine(parent.FullName,"Cargo.toml")))root=parent.FullName;
            for(int i=0;i<args.Length;i++) {
                if(args[i]=="--workspace" && i+1<args.Length)root=Path.GetFullPath(args[++i]);
                else if(args[i]=="--self-test")selfTest=true;
                else throw new ArgumentException("Usage: BoomLauncher.exe [--workspace <directory>]");
            }
            if(!File.Exists(backend))throw new FileNotFoundException("boom.exe must be beside BoomLauncher.exe");
            if(selfTest)return SelfTest(root,backend);
            Directory.CreateDirectory(root); Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            using(var form=new LauncherForm(root,backend))Application.Run(form);
            return 0;
        } catch(Exception error) {if(selfTest)Console.Error.WriteLine(error.ToString());else MessageBox.Show(error.Message,"BoomMinecraft Launcher",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
    }
}
