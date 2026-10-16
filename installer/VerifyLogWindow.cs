using System;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows.Forms;

class VerifyLogWindow {
    static Exception uiError;
    static object Field(object target,string name) {return target.GetType().GetField(name,BindingFlags.Instance|BindingFlags.NonPublic).GetValue(target);}
    static void Call(object target,string name,params object[] args) {target.GetType().GetMethod(name,BindingFlags.Instance|BindingFlags.NonPublic).Invoke(target,args);}
    static void Pump() {for(int i=0;i<12;i++){Application.DoEvents();System.Threading.Thread.Sleep(5);}if(uiError!=null)throw new Exception("UI callback failed",uiError);}
    static void Require(bool condition,string message) {if(!condition)throw new Exception(message);}
    [STAThread] static int Main(string[] args) {
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException+=(s,e)=>uiError=e.Exception;
        try {
            var asm=Assembly.LoadFrom(args[0]);
            var type=asm.GetType("SetupForm");
            var form=(Form)Activator.CreateInstance(type,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,new object[]{System.IO.Path.GetTempPath()},null);
            form.Opacity=0;form.ShowInTaskbar=false;form.Show();Pump();
            Call(form,"UpdateLine","before-open");Pump();
            for(int n=0;n<30;n++) {
                Call(form,"ShowDetails");Pump();
                var view=(TextBox)Field(form,"details");
                Require(view.Text.Contains("before-open"),"Previous log is missing");
                var dialog=view.FindForm();dialog.Opacity=0;dialog.ShowInTaskbar=false;
                // Queue worker output, then close its view before UI dispatch.
                Task.Run(()=>Call(form,"UpdateLine","queued-"+n)).Wait();
                dialog.Close();Pump();
                Task.Run(()=>Call(form,"UpdateLine","closed-"+n)).Wait();Pump();
            }
            Call(form,"ShowDetails");Pump();
            var finalView=(TextBox)Field(form,"details");
            Require(finalView.Text.Contains("queued-29") && finalView.Text.Contains("closed-29"),"Closed-window output lost");
            Call(form,"UpdateLine","STAGE:4:model-download");Pump();
            Require(((Label)Field(form,"status")).Text.Contains("4/6"),"Stage display stopped");
            Call(form,"UpdateLine",new string('x',160000));Pump();
            Call(form,"UpdateLine","after-trim");Pump();
            Require(((TextBox)Field(form,"details")).Text.EndsWith("after-trim"+Environment.NewLine),"Log trim failed");
            Call(form,"UpdateLine","queued-before-dispose");form.Dispose();Pump();
            Task.Run(()=>Call(form,"UpdateLine","after-dispose")).Wait();Pump();
            Console.WriteLine("PASS: 30 close/reopen cycles, queued and closed-window output, progress, trim, disposal");
            return 0;
        } catch(Exception ex) {Console.WriteLine("FAIL: "+ex);return 1;}
    }
}
