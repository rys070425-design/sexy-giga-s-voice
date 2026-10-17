using System;
using System.Reflection;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
class VerifyLanguageSetup {
 static object Field(object target,string name){return target.GetType().GetField(name,BindingFlags.NonPublic|BindingFlags.Instance).GetValue(target);}
 static void Require(bool good,string text){if(!good)throw new Exception(text);}
 [STAThread] static int Main(string[] args){
  try{
   Application.EnableVisualStyles();
   var asm=Assembly.LoadFrom(args[0]);var type=asm.GetType("SetupForm");var ui=asm.GetType("SetupUi");
   var form=(Form)Activator.CreateInstance(type,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,new object[]{"C:\\Test\\UniversalVoiceKR"},null);
   form.ShowInTaskbar=false;form.Show();Application.DoEvents();
   var combo=(ComboBox)Field(form,"language");var title=(Label)Field(form,"title");
   Require(combo.Items.Count==25,"Pack language count mismatch");
   Require((string)ui.GetField("Code").GetValue(null)=="en","Installer must begin in English");
   Require(title.Text=="Live translation, in your language.","English introduction missing");
   Directory.CreateDirectory(args[1]);
   for(int i=0;i<combo.Items.Count;i++){
    combo.SelectedIndex=i;Application.DoEvents();
    string code=(string)combo.SelectedItem.GetType().GetField("Code").GetValue(combo.SelectedItem);
    string json=(string)ui.GetMethod("PreferencesJson").Invoke(null,null);
    Require(json.Contains("\"ui_language\":\""+code+"\"")&&json.Contains("\"caption_language\":\""+code+"\"")&&json.Contains("\"hide_native\":true"),"Preferences mismatch: "+code);
    Require(!String.IsNullOrEmpty(title.Text),"Empty localized introduction");
    if(code=="ko")Require(title.Text=="음성 자막, 처음부터 간편하게.","Korean not applied immediately");
    if(code=="en"||code=="ko"||code=="ja"||code=="ar"){
     using(var bitmap=new Bitmap(form.Width,form.Height)){form.DrawToBitmap(bitmap,new Rectangle(Point.Empty,form.Size));bitmap.Save(Path.Combine(args[1],"installer-"+code+".png"));}
    }
   }
   combo.SelectedIndex=1;Application.DoEvents();Require(title.Text=="Live translation, in your language.","English restore failed");
   form.Dispose();Console.WriteLine("INSTALLER_25_LANGUAGES_AND_PREFERENCES_VERIFIED");return 0;
  }catch(Exception e){Console.WriteLine(e);return 1;}
 }
}
