using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Web.Script.Serialization;

[assembly: AssemblyTitle("Universal Voice KR Setup")]
[assembly: AssemblyDescription("Universal Voice KR 0.9 multilingual readable subtitles")]
[assembly: AssemblyVersion("0.9.3.0")]
[assembly: AssemblyFileVersion("0.9.3.0")]

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
                File.WriteAllText(Path.Combine(root,"install_preferences.json"),SetupUi.PreferencesJson(),new UTF8Encoding(false));
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
            else if(args[i]=="/language" && i+1<args.Length) SetupUi.Select(args[++i]);
        }
        if(silent) return Install(root,shortcuts,s=>{});
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SetupForm(root)); return 0;
    }
}

class LanguageChoice {
    public string Code,Name;
    public override string ToString(){return Name;}
}

static class SetupUi {
    static readonly Dictionary<string,object> messages;
    public static readonly List<LanguageChoice> Languages=new List<LanguageChoice>();
    public static string Code="en";
    static SetupUi(){
        using(var resource=Assembly.GetExecutingAssembly().GetManifestResourceStream("ui_locales.json"))
        using(var reader=new StreamReader(resource,Encoding.UTF8)){
            var root=(Dictionary<string,object>)new JavaScriptSerializer(){MaxJsonLength=8*1024*1024}.DeserializeObject(reader.ReadToEnd());
            messages=(Dictionary<string,object>)root["messages"];
            foreach(var raw in (object[])root["languages"]){
                var item=(Dictionary<string,object>)raw;
                Languages.Add(new LanguageChoice{Code=(string)item["code"],Name=(string)item["name"]});
            }
        }
    }
    public static void Select(string code){
        Code=Languages.Exists(item=>item.Code==code)?code:"en";
    }
    public static string Text(string source){
        if(Code=="ko")return source;
        object raw;string code=Code=="pb"?"pt":Code;
        var english=(Dictionary<string,object>)messages["en"];
        var selected=messages.TryGetValue(code,out raw)?(Dictionary<string,object>)raw:english;
        if(selected.TryGetValue(source,out raw))return (string)raw;
        if(english.TryGetValue(source,out raw))return (string)raw;
        return source;
    }
    public static string PreferencesJson(){
        return new JavaScriptSerializer().Serialize(new Dictionary<string,object>{
            {"schema",1},{"ui_language",Code},{"caption_language",Code},{"hide_native",true}});
    }
}

class SetupForm : Form {
    TextBox path, details; Label status, intro,title,locationLabel,internetNote; ProgressBar progress; Button install, cancel, detailButton; CheckBox launch;
    ComboBox language;
    string lastStatus="설치할 준비가 되었습니다.";
    int currentStage=0;
    bool retry=false;
    Form detailsDialog;
    readonly StringBuilder logText = new StringBuilder();
    bool running=false, done=false;
    Color bg=Color.FromArgb(17,21,28), panel=Color.FromArgb(27,35,46), mint=Color.FromArgb(121,227,192);
    public SetupForm(string root) {
        Text=SetupUi.Text("Universal Voice KR · 설치"); ClientSize=new Size(680,570); MinimumSize=Size; MaximumSize=Size;
        StartPosition=FormStartPosition.CenterScreen; MaximizeBox=false; BackColor=bg; ForeColor=Color.FromArgb(233,237,245);
        Icon=Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        Font=new Font("Malgun Gothic",10f); AutoScaleMode=AutoScaleMode.Dpi;
        Label brand=LabelAt("voice",32,22,500,56,31f,mint); brand.Font=new Font("Segoe UI",31f,FontStyle.Bold);
        LabelAt("UNIVERSAL KR  /  0.9.3",35,82,500,24,9f,Color.FromArgb(150,166,185));
        LabelAt("NLLB: CC-BY-NC-4.0",35,105,500,18,8f,Color.FromArgb(150,166,185));
        LabelAt("Language",34,128,150,30,10f,ForeColor);
        language=new ComboBox{Left=196,Top=124,Width=448,DropDownStyle=ComboBoxStyle.DropDownList,BackColor=panel,ForeColor=ForeColor,FlatStyle=FlatStyle.Flat};
        foreach(var choice in SetupUi.Languages)language.Items.Add(choice);
        language.SelectedIndex=SetupUi.Languages.FindIndex(item=>item.Code==SetupUi.Code);
        Controls.Add(language);
        title=LabelAt("",32,180,610,42,19f,ForeColor);
        intro=LabelAt("",34,229,610,64,10f,Color.FromArgb(170,183,201));
        locationLabel=LabelAt("",34,301,600,23,9f,Color.FromArgb(150,166,185));
        path=new TextBox {Left=34,Top=329,Width=610,Height=30,Text=root,BackColor=panel,ForeColor=ForeColor,BorderStyle=BorderStyle.FixedSingle}; Controls.Add(path);
        internetNote=LabelAt("",34,368,610,30,9f,Color.FromArgb(150,166,185));
        status=LabelAt("",34,411,610,25,10f,ForeColor);
        progress=new ProgressBar {Left=34,Top=445,Width=610,Height=7,Minimum=0,Maximum=7,Value=0}; Controls.Add(progress);
        install=ButtonAt("",474,490,170,mint,Color.FromArgb(9,37,30)); install.Click+=async(s,e)=>await StartInstall();
        AcceptButton=install;Shown+=(s,e)=>{install.Focus();path.SelectionStart=0;path.SelectionLength=0;};
        cancel=ButtonAt("",350,490,110,panel,ForeColor); cancel.Click+=(s,e)=>{if(running){Setup.Cancel();lastStatus="설치를 취소하는 중입니다.";ApplyLanguage();} else Close();};
        detailButton=ButtonAt("",34,490,220,panel,ForeColor); detailButton.Click+=(s,e)=>ShowDetails();
        launch=new CheckBox {Left=34,Top=407,Width=600,Checked=true,Visible=false}; Controls.Add(launch);
        FormClosing+=(s,e)=>{if(running){Setup.Cancel();e.Cancel=true;lastStatus="설치를 취소하는 중입니다.";ApplyLanguage();}};
        language.SelectedIndexChanged+=(s,e)=>{SetupUi.Select(((LanguageChoice)language.SelectedItem).Code);ApplyLanguage();};
        ApplyLanguage();
    }
    void ApplyLanguage(){
        Func<string,string> L=SetupUi.Text;
        RightToLeft=(SetupUi.Code=="ar"||SetupUi.Code=="fa")?RightToLeft.Yes:RightToLeft.No;
        RightToLeftLayout=RightToLeft==RightToLeft.Yes;
        path.RightToLeft=RightToLeft.No;language.RightToLeft=RightToLeft.No;
        Text=L("Universal Voice KR · 설치");title.Text=L("음성 자막, 처음부터 간편하게.");
        intro.Text=L(done?"설치와 실행 환경 검사가 완료되었습니다.\nDiscord 닉네임 연결은 앱에서 직접 승인해 주세요.":"기존 앱이 없어도 설치할 수 있습니다.\n실행 환경 · 음성 모델 · 다국어 번역(비상업용 모델)을 준비합니다.");
        locationLabel.Text=L("설치 위치");internetNote.Text=L("인터넷 연결 필요 · 구성에 따라 수 GB 다운로드 · 관리자 권한 불필요");
        install.Text=L(done?"시작하기":retry?"다시 시도":"설치");
        cancel.Text=L(running?"설치 취소":"닫기");detailButton.Text=L("설치 내역");launch.Text=L("완료 후 Universal Voice KR 실행");
        status.Text=L(lastStatus)+(currentStage>0?" ("+currentStage+"/6)":"");
        if(detailsDialog!=null&&!detailsDialog.IsDisposed)detailsDialog.Text=L("설치 내역");
    }
    Label LabelAt(string text,int x,int y,int w,int h,float size,Color color) {var label=new Label {Text=text,Left=x,Top=y,Width=w,Height=h,ForeColor=color,Font=new Font("Malgun Gothic",size)};Controls.Add(label);return label;}
    Button ButtonAt(string text,int x,int y,int w,Color color,Color foreground) {var button=new Button {Text=text,Left=x,Top=y,Width=w,Height=42,BackColor=color,ForeColor=foreground,FlatStyle=FlatStyle.Flat};button.FlatAppearance.BorderSize=0;Controls.Add(button);return button;}
    void ShowDetails() {
        if(detailsDialog!=null && !detailsDialog.IsDisposed){detailsDialog.Activate();return;}
        var dialog=new Form {Text=SetupUi.Text("설치 내역"),Width=850,Height=460,StartPosition=FormStartPosition.CenterParent,BackColor=bg};
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
        if(line.StartsWith("STAGE:")) {var parts=line.Split(new[]{':'},3);int stage;if(parts.Length==3 && Int32.TryParse(parts[1],out stage)){progress.Value=Math.Min(6,stage);currentStage=stage;lastStatus=parts[2];ApplyLanguage();}}
        if(line.StartsWith("INSTALL_ERROR:")){currentStage=0;lastStatus=line.Substring(14).Trim();ApplyLanguage();}
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
        try {target=Path.GetFullPath(path.Text.Trim()); if(target.Contains("\""))throw new Exception();} catch {lastStatus="설치 위치를 확인하세요.";ApplyLanguage();return;}
        path.Text=target;path.Enabled=false;language.Enabled=false;running=true;Setup.Cancelled=false;install.Enabled=false;ApplyLanguage();
        int code=await Task.Run(()=>Setup.Install(target,true,UpdateLine));
        if(IsDisposed || Disposing)return;
        running=false;install.Enabled=true;
        if(code==0){done=true;progress.Value=7;status.Visible=false;launch.Visible=true;}
        else {path.Enabled=true;language.Enabled=true;retry=true;currentStage=0;lastStatus=code==2?"설치가 취소되었습니다. 다시 실행하면 이어서 준비합니다.":"설치가 완료되지 않았습니다. 설치 내역을 확인하고 다시 시도하세요.";}
        ApplyLanguage();
    }
}
