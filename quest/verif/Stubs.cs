// Stubs minimaux des API Unity / Meta XR, signatures reprises des vraies : verifie syntaxe et types des scripts du
// casque SANS Unity (`cd quest/verif && dotnet build`). Ne remplace pas la compilation dans Unity : les noms exacts
// des API du kit Meta (MRUK, OVRInput) ne sont verifies que la-bas.
using System;
using System.Collections;
using System.Collections.Generic;

namespace UnityEngine.Events { public delegate void UnityAction(); }

namespace UnityEngine
{
    public class Object
    {
        public string name { get; set; }
        public static void Destroy(Object o) { }
        public static T FindFirstObjectByType<T>() where T : Object => null;
        public static implicit operator bool(Object o) => o != null;
    }
    public class Component : Object
    {
        public Transform transform => null;
        public GameObject gameObject => null;
        public T GetComponent<T>() => default;
        public T[] GetComponents<T>() => null;
    }
    public class Behaviour : Component { public bool enabled { get; set; } }
    public class Coroutine { }
    public class MonoBehaviour : Behaviour { public Coroutine StartCoroutine(IEnumerator r) => null; }
    public enum PrimitiveType { Sphere, Capsule, Cylinder, Cube, Plane, Quad }
    public class GameObject : Object
    {
        public GameObject() { }
        public GameObject(string name) { }
        public Transform transform => null;
        public T AddComponent<T>() where T : Component => null;
        public T GetComponent<T>() => default;
        public void SetActive(bool v) { }
        public bool activeSelf => true;
        public static GameObject CreatePrimitive(PrimitiveType t) => null;
    }
    public class Transform : Component, IEnumerable
    {
        public Vector3 position { get; set; }
        public Quaternion rotation { get; set; }
        public Vector3 localPosition { get; set; }
        public Quaternion localRotation { get; set; }
        public Vector3 localScale { get; set; }
        public Vector3 forward { get; set; }
        public Vector3 up { get; set; }
        public Vector3 right { get; set; }
        public Matrix4x4 localToWorldMatrix => default;
        public void SetParent(Transform p, bool worldPositionStays) { }
        public void SetParent(Transform p) { }
        public void SetPositionAndRotation(Vector3 p, Quaternion q) { }
        public IEnumerator GetEnumerator() => null;
    }
    public class Shader : Object { public static Shader Find(string n) => null; }
    public class Texture : Object { public int width => 0; public int height => 0; }
    public class Texture2D : Texture { }
    public class Material : Object
    {
        public Material(Shader s) { }
        public Color color { get; set; }
        public Texture mainTexture { get; set; }
        public bool HasProperty(string n) => false;
        public void SetFloat(string n, float v) { }
    }
    public class Renderer : Component { public Material material { get; set; } public Material sharedMaterial { get; set; } }
    public class MeshRenderer : Renderer { }
    public class LineRenderer : Renderer
    {
        public Color startColor { get; set; }
        public Color endColor { get; set; }
        public float startWidth { get; set; }
        public float endWidth { get; set; }
        public int positionCount { get; set; }
        public bool loop { get; set; }
        public void SetPosition(int i, Vector3 p) { }
    }
    public class Mesh : Object
    {
        public Vector3[] vertices { get; set; }
        public Vector3[] normals { get; set; }
        public int[] triangles { get; set; }
        public void RecalculateBounds() { }
    }
    public class MeshFilter : Component { public Mesh sharedMesh { get; set; } public Mesh mesh { get; set; } }
    public class Collider : Component { }
    public class MeshCollider : Collider { public Mesh sharedMesh { get; set; } }
    public struct RaycastHit { public Collider collider => null; public Vector3 point => default; public float distance => 0; }
    public static class Physics { public static bool Raycast(Vector3 o, Vector3 d, out RaycastHit h, float max) { h = default; return false; } }
    public class Camera : Behaviour { public static Camera main => null; }
    public enum TextAnchor { UpperLeft, MiddleCenter }
    public enum TextAlignment { Left, Center, Right }
    public class Font : Object { public Material material => null; }
    public class TextMesh : Component
    {
        public string text { get; set; }
        public Color color { get; set; }
        public float characterSize { get; set; }
        public int fontSize { get; set; }
        public TextAnchor anchor { get; set; }
        public TextAlignment alignment { get; set; }
        public Font font { get; set; }
    }
    public class AudioClip : Object { }
    public class AudioSource : Behaviour
    {
        public float spatialBlend { get; set; }
        public float minDistance { get; set; }
        public void PlayOneShot(AudioClip c) { }
    }
    public static class Resources
    {
        public static T Load<T>(string p) where T : Object => null;
        public static T GetBuiltinResource<T>(string p) where T : Object => null;
    }
    public static class SystemInfo { public static string deviceModel => ""; public static string deviceName => ""; }
    public static class PlayerPrefs
    {
        public static bool HasKey(string k) => false; public static string GetString(string k) => "";
        public static void SetString(string k, string v) { } public static void Save() { }
    }
    public enum TouchScreenKeyboardType { Default, ASCIICapable, NumbersAndPunctuation, URL, NumberPad, PhonePad, NamePhonePad, EmailAddress }
    public class TouchScreenKeyboard
    {
        public enum Status { Visible, Done, Canceled, LostFocus }
        public static TouchScreenKeyboard Open(string text, TouchScreenKeyboardType type, bool autocorrection, bool multiline, bool secure) => null;
        public string text { get; set; }
        public Status status => Status.Visible;
    }
    public static class Application { public static string persistentDataPath => ""; }
    public static class Debug { public static void Log(object m) { } }
    public static class Time { public static float time => 0; public static float deltaTime => 0; }
    public static class ColorUtility { public static bool TryParseHtmlString(string s, out Color c) { c = default; return false; } }
    public class TooltipAttribute : Attribute { public TooltipAttribute(string t) { } }
    public class HideInInspector : Attribute { }
    public struct Rect { public float x, y, width, height; public float xMin => 0; public float yMin => 0; public float xMax => 0; public float yMax => 0; public Vector2 center => default; public Vector2 size => default; }
    public struct Bounds { public Vector3 center => default; public Vector3 size => default; public Vector3 min => default; public Vector3 max => default; public Vector3 extents => default; }
    public struct Matrix4x4 { public float this[int r, int c] => 0; public Vector3 MultiplyPoint3x4(Vector3 p) => p; public Vector3 MultiplyVector(Vector3 p) => p; }
    public struct Color
    {
        public float r, g, b, a;
        public Color(float r, float g, float b, float a = 1f) { this.r = r; this.g = g; this.b = b; this.a = a; }
        public static Color gray => default; public static Color white => default; public static Color red => default;
    }
    public struct Vector2
    {
        public float x, y;
        public Vector2(float x, float y) { this.x = x; this.y = y; }
    }
    public struct Vector3
    {
        public float x, y, z;
        public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; }
        public static Vector3 zero => default; public static Vector3 one => default; public static Vector3 up => default;
        public static Vector3 forward => default; public static Vector3 left => default; public static Vector3 right => default;
        public Vector3 normalized => this; public float magnitude => 0;
        public static float Dot(Vector3 a, Vector3 b) => 0;
        public static float Distance(Vector3 a, Vector3 b) => 0;
        public static Vector3 Lerp(Vector3 a, Vector3 b, float t) => a;
        public static Vector3 Cross(Vector3 a, Vector3 b) => a;
        public static Vector3 operator +(Vector3 a, Vector3 b) => a;
        public static Vector3 operator -(Vector3 a, Vector3 b) => a;
        public static Vector3 operator -(Vector3 a) => a;
        public static Vector3 operator *(float k, Vector3 a) => a;
        public static Vector3 operator *(Vector3 a, float k) => a;
        public static Vector3 operator /(Vector3 a, float k) => a;
    }
    public struct Quaternion
    {
        public float x, y, z, w;
        public static Quaternion identity => default;
        public Vector3 eulerAngles => default;
        public static Quaternion LookRotation(Vector3 f, Vector3 u) => default;
        public static Quaternion LookRotation(Vector3 f) => default;
        public static Quaternion Inverse(Quaternion q) => q;
        public static Quaternion Slerp(Quaternion a, Quaternion b, float t) => a;
        public static Quaternion Euler(float x, float y, float z) => default;
        public static Quaternion operator *(Quaternion a, Quaternion b) => a;
        public static Vector3 operator *(Quaternion a, Vector3 v) => v;
    }
    public static class Mathf
    {
        public const float Deg2Rad = 0.0174532924f, Rad2Deg = 57.29578f, PI = 3.14159274f;
        public static float Abs(float v) => v; public static float Sqrt(float v) => v; public static float Exp(float v) => v;
        public static float Sin(float v) => v; public static float Cos(float v) => v; public static float Atan2(float y, float x) => y;
        public static float Max(float a, float b) => a; public static float Min(float a, float b) => a;
        public static int Max(int a, int b) => a; public static int Min(int a, int b) => a;
        public static float Clamp(float v, float a, float b) => v; public static int Clamp(int v, int a, int b) => v;
        public static float DeltaAngle(float a, float b) => a; public static int RoundToInt(float v) => 0;
    }
}

namespace UnityEngine.Networking
{
    public class DownloadHandler { public string text => ""; public byte[] data => null; }
    public class DownloadHandlerBuffer : DownloadHandler { }
    public class DownloadHandlerTexture : DownloadHandler { public static Texture2D GetContent(UnityWebRequest r) => null; }
    public class UploadHandler { }
    public class UploadHandlerRaw : UploadHandler { public UploadHandlerRaw(byte[] d) { } }
    public class UnityWebRequestAsyncOperation { }
    public class UnityWebRequest : IDisposable
    {
        public enum Result { InProgress, Success, ConnectionError, ProtocolError, DataProcessingError }
        public UnityWebRequest(string url, string method) { }
        public static UnityWebRequest Get(string url) => null;
        public UnityWebRequestAsyncOperation SendWebRequest() => null;
        public void SetRequestHeader(string k, string v) { }
        public int timeout { get; set; }
        public Result result => Result.Success;
        public string error => "";
        public long responseCode => 0;
        public DownloadHandler downloadHandler { get; set; }
        public UploadHandler uploadHandler { get; set; }
        public void Dispose() { }
    }
    public static class UnityWebRequestTexture { public static UnityWebRequest GetTexture(string u) => null; }
}

public static class OVRInput
{
    public enum Button { One, Two, Three, Four, PrimaryIndexTrigger, PrimaryHandTrigger, PrimaryThumbstick }
    public enum Axis2D { PrimaryThumbstick, SecondaryThumbstick }
    public enum Controller { LTouch, RTouch, Touch }
    public static bool Get(Button b, Controller c) => false;
    public static bool GetDown(Button b, Controller c) => false;
    public static bool GetUp(Button b, Controller c) => false;
    public static UnityEngine.Vector2 Get(Axis2D a, Controller c) => default;
}
public class OVRCameraRig : UnityEngine.MonoBehaviour { public UnityEngine.Transform rightControllerAnchor => null; }

namespace Meta.XR.MRUtilityKit
{
    public class MRUKAnchor : UnityEngine.MonoBehaviour { }
    public class MRUK : UnityEngine.MonoBehaviour
    {
        public static MRUK Instance => null;
        public void RegisterSceneLoadedCallback(UnityEngine.Events.UnityAction a) { }
    }
}
