using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("Universal Voice KR Setup")]
[assembly: AssemblyDescription("Universal Voice KR 0.8 multilingual readable subtitles")]
[assembly: AssemblyVersion("0.8.1.0")]
[assembly: AssemblyFileVersion("0.8.1.0")]

static class Setup {
    public static string DefaultRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "UniversalVoiceKR_05");
    public static volatile Process Child;
    public static volatile bool Cancelled;
    public static string Quote(string value) { return "\"" + value.Replace("\"", "\\\"").TrimEnd('\\') + "\""; }
    public static int Install(string root, bool shortcuts, Action<string> line) {
        if(Cancelled)return 2;
        string staging;
        FileStream installLock=null;
        StreamWriter installLog;
        try {
            root = Path.GetFullPath(root);
            Directory.CreateDirectory(root);
            staging = Path.Combine(root, ".installer");
            Directory.CreateDirectory(staging);
            installLock = new FileStream(Path.Combine(staging,"installation.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
            installLog = new StreamWriter(Path.Combine(root,"installation.log"),false,new UTF8Encoding(false));
        } catch(Exception ex) {if(installLock!=null)installLock.Dispose();line("INSTALL_ERROR: 설치 위치를 사용할 수 없거나 다른 설치가 진행 중입니다. " + ex.Message);return 1;}
        using(installLock)
        using (var log = installLog) {
            object sync = new object();
            Action<string> report = s => { if (s == null) return; lock(sync) { log.WriteLine(s); log.Flush(); } line(s); };
            try {
                using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
                using (var zip = new ZipArchive(resource, ZipArchiveMode.Read)) {
                    foreach (var entry in zip.Entries) {
                        if(Cancelled)return 2;
                        var dest = Path.GetFullPath(Path.Combine(root, entry.FullName));
                        if (!dest.StartsWith(root.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase)) throw new Exception("Invalid payload path");
                        if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(dest); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(dest));
                        using(var input = entry.Open()) using(var output = File.Create(dest)) input.CopyTo(output);
                    }
                }
                string script = Path.Combine(staging, "bootstrap.ps1");
                using(var input = Assembly.GetExecutingAssembly().GetManifestResourceStream("bootstrap.ps1"))
                using(var output = File.Create(script)) input.CopyTo(output);
                var info = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe"));
                info.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File " + Quote(script) + " -InstallRoot " + Quote(root) + (shortcuts ? "" : " -NoShortcuts");
                info.UseShellExecute = false; info.CreateNoWindow = true;
                info.RedirectStandardOutput = true; info.RedirectStandardError = true;
                info.StandardOutputEncoding = Encoding.UTF8; info.StandardErrorEncoding = Encoding.UTF8;
                // A parent PowerShell 7 process may export incompatible module
                // search paths. Use the matching Windows PowerShell 5 modules.
                info.EnvironmentVariables["PSModulePath"] = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell","v1.0","Modules");
                info.WorkingDirectory = root;
                using(var child = new Process()) {
                    if(Cancelled)return 2;
                    Child = child; child.StartInfo = info;
                    child.OutputDataReceived += (s,e) => report(e.Data);
                    child.ErrorDataReceived += (s,e) => report(e.Data);
                    child.Start(); child.BeginOutputReadLine(); child.BeginErrorReadLine();
                    if(Cancelled)Cancel();
                    child.WaitForExit(); child.WaitForExit();
                    int code = child.ExitCode; Child = null;
                    if (Cancelled) return 2;
                    if (code == 0 && !File.Exists(Path.Combine(root,"INSTALL_SUCCESS.json"))) return 1;
                    return code;
                }
            } catch(Exception ex) { report("INSTALL_ERROR: " + ex.Message); return 1; }
        }
    }
    public static void Cancel() {
        Cancelled = true;
        try {
            if (Child != null && !Child.HasExited) {
                var start = new ProcessStartInfo("taskkill.exe", "/PID " + Child.Id + " /T /F");
                start.UseShellExecute=false; start.CreateNoWindow=true;
                using(var p = Process.Start(start)) p.WaitForExit();
            }
        } catch { }
    }
    public static void Launch(string root) {
        var start = new ProcessStartInfo(Path.Combine(root,".venv","Scripts","pythonw.exe"), Quote(Path.Combine(root,"launch.py")));
        start.UseShellExecute=false; start.CreateNoWindow=true; start.WorkingDirectory=root;
        Process.Start(start);
    }
    [STAThread] public static int Main(string[] args) {
        string root=DefaultRoot; bool silent=false, shortcuts=true;
        for(int i=0;i<args.Length;i++) {
            if(args[i]=="/silent") silent=true;
            else if(args[i]=="/no-shortcuts") shortcuts=false;
            else if(args[i]=="/target" && i+1<args.Length) root=args[++i];
        }
        if(silent) return Install(root,shortcuts,s=>{});
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SetupForm(root)); return 0;
    }
}

class SetupForm : Form {
    TextBox path, details; Label status, intro; ProgressBar progress; Button install, cancel, detailButton; CheckBox launch;
    Form detailsDialog;
    readonly StringBuilder logText = new StringBuilder();
    bool running=false, done=false;
    Color bg=Color.FromArgb(17,21,28), panel=Color.FromArgb(27,35,46), mint=Color.FromArgb(121,227,192);
    public SetupForm(string root) {
        Text="Universal Voice KR · 설치"; ClientSize=new Size(680,520); MinimumSize=Size; MaximumSize=Size;
        StartPosition=FormStartPosition.CenterScreen; MaximizeBox=false; BackColor=bg; ForeColor=Color.FromArgb(233,237,245);
        Icon=Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        Font=new Font("Malgun Gothic",10f); AutoScaleMode=AutoScaleMode.Dpi;
        Label brand=LabelAt("voice",32,22,500,56,31f,mint); brand.Font=new Font("Segoe UI",31f,FontStyle.Bold);
        LabelAt("UNIVERSAL KR  /  0.8.1",35,82,500,24,9f,Color.FromArgb(150,166,185));
        LabelAt("음성 자막, 처음부터 간편하게.",32,132,610,38,19f,ForeColor);
        intro=LabelAt("기존 앱이 없어도 설치할 수 있습니다.\n실행 환경 · 음성 모델 · 다국어 번역(비상업용 모델)을 준비합니다.",34,181,610,58,10f,Color.FromArgb(170,183,201));
        LabelAt("설치 위치",34,254,600,23,9f,Color.FromArgb(150,166,185));
        path=new TextBox {Left=34,Top=282,Width=610,Height=30,Text=root,BackColor=panel,ForeColor=ForeColor,BorderStyle=BorderStyle.FixedSingle}; Controls.Add(path);
        LabelAt("인터넷 연결 필요 · 구성에 따라 수 GB 다운로드 · 관리자 권한 불필요",34,321,610,28,9f,Color.FromArgb(150,166,185));
        status=LabelAt("설치할 준비가 되었습니다.",34,366,610,25,10f,ForeColor);
        progress=new ProgressBar {Left=34,Top=400,Width=610,Height=7,Minimum=0,Maximum=7,Value=0}; Controls.Add(progress);
        install=ButtonAt("설치",474,444,170,mint,Color.FromArgb(9,37,30)); install.Click+=async(s,e)=>await StartInstall();
        AcceptButton=install;Shown+=(s,e)=>{install.Focus();path.SelectionStart=0;path.SelectionLength=0;};
        cancel=ButtonAt("닫기",350,444,110,panel,ForeColor); cancel.Click+=(s,e)=>{if(running){Setup.Cancel(); status.Text="설치를 취소하는 중입니다.";} else Close();};
        detailButton=ButtonAt("설치 내역",34,444,120,panel,ForeColor); detailButton.Click+=(s,e)=>ShowDetails();
        launch=new CheckBox {Left=34,Top=362,Width=400,Text="완료 후 Universal Voice KR 실행",Checked=true,Visible=false}; Controls.Add(launch);
        FormClosing+=(s,e)=>{if(running){Setup.Cancel(); e.Cancel=true; status.Text="설치를 취소하는 중입니다.";}};
    }
    Label LabelAt(string text,int x,int y,int w,int h,float size,Color color) {var label=new Label {Text=text,Left=x,Top=y,Width=w,Height=h,ForeColor=color,Font=new Font("Malgun Gothic",size)};Controls.Add(label);return label;}
    Button ButtonAt(string text,int x,int y,int w,Color color,Color foreground) {var button=new Button {Text=text,Left=x,Top=y,Width=w,Height=42,BackColor=color,ForeColor=foreground,FlatStyle=FlatStyle.Flat};button.FlatAppearance.BorderSize=0;Controls.Add(button);return button;}
    void ShowDetails() {
        if(detailsDialog!=null && !detailsDialog.IsDisposed){detailsDialog.Activate();return;}
        var dialog=new Form {Text="설치 내역",Width=850,Height=460,StartPosition=FormStartPosition.CenterParent,BackColor=bg};
        var view=new TextBox {Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,WordWrap=false,BackColor=panel,ForeColor=ForeColor,Font=new Font("Consolas",9),Dock=DockStyle.Fill,Text=logText.ToString()};
        detailsDialog=dialog; details=view;
        dialog.Controls.Add(view);
        dialog.FormClosed+=(s,e)=>{if(ReferenceEquals(detailsDialog,dialog)){details=null;detailsDialog=null;}};
        dialog.Show(this);
    }
    void ApplyLine(string line) {
        if(IsDisposed || Disposing)return;
        // Keep the log independently of the optional window. Closing that
        // window disposes its TextBox while installation continues.
        if(logText.Length>150000)logText.Remove(0,50000);
        logText.AppendLine(line);
        if(details!=null && !details.IsDisposed) {
            if(details.TextLength>150000)details.Text=details.Text.Substring(50000);
            details.AppendText(line+Environment.NewLine);
        }
        if(line.StartsWith("STAGE:")) {var parts=line.Split(new[]{':'},3);int stage;if(parts.Length==3 && Int32.TryParse(parts[1],out stage)){progress.Value=Math.Min(6,stage);status.Text=parts[2]+" ("+stage+"/6)";}}
        if(line.StartsWith("INSTALL_ERROR:"))status.Text=line.Substring(14).Trim();
    }
    void UpdateLine(string line) {
        if(line==null || IsDisposed || Disposing || !IsHandleCreated)return;
        try {BeginInvoke((Action)(()=>ApplyLine(line)));}
        catch(InvalidOperationException) {if(!IsDisposed && !Disposing && IsHandleCreated)throw;}
    }
    async Task StartInstall() {
        if(done) {if(launch.Checked) Setup.Launch(path.Text);Close();return;}
        if(running)return;
        string target;
        try {target=Path.GetFullPath(path.Text.Trim()); if(target.Contains("\""))throw new Exception();} catch {status.Text="설치 위치를 확인하세요.";return;}
        path.Text=target;path.Enabled=false;running=true;Setup.Cancelled=false;install.Enabled=false;cancel.Text="설치 취소";
        int code=await Task.Run(()=>Setup.Install(target,true,UpdateLine));
        if(IsDisposed || Disposing)return;
        running=false;cancel.Text="닫기";install.Enabled=true;
        if(code==0){done=true;progress.Value=7;status.Visible=false;launch.Visible=true;intro.Text="설치와 실행 환경 검사가 완료되었습니다.\nDiscord 닉네임 연결은 앱에서 직접 승인해 주세요.";install.Text="시작하기";}
        else {path.Enabled=true;install.Text="다시 시도";status.Text=code==2?"설치가 취소되었습니다. 다시 실행하면 이어서 준비합니다.":"설치가 완료되지 않았습니다. 설치 내역을 확인하고 다시 시도하세요.";}
    }
}
