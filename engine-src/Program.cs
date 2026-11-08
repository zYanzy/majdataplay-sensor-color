using System;
using System.Globalization;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

// MajdataPlay 2.0.3 -- sensor highlight color IL patcher.
//
//   patcher <input.dll> --inspect
//       -> prints JSON: {"r":..,"g":..,"b":..,"a":..}
//
//   patcher <input.dll> <output.dll> --color R,G,B,A
//       -> rewrites ONLY the active-state Color(...) in
//          DummyTouchPanelRenderer.OnPreUpdate(). Components are 0..1;
//          omitting --color uses (1,0,0,0.3).
//
// This engine touches ONLY DummyTouchPanelRenderer. It never reads or writes
// BGInfoOption / ObjectCounter, so it is completely independent from the
// Fault counter patch: either one can be installed alone, or both in any
// order. It is idempotent: running it again on an already-colored DLL just
// writes the new color.

internal static class Program
{
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    private static int Main(string[] args)
    {
        try { return Run(args); }
        catch (Exception ex)
        {
            Console.Error.WriteLine("ERROR: " + ex.Message);
            return 1;
        }
    }

    private static void Usage()
    {
        Console.Error.WriteLine("usage:");
        Console.Error.WriteLine("  patcher <input.dll> --inspect");
        Console.Error.WriteLine("  patcher <input.dll> <output.dll> --color R,G,B,A");
    }

    private static string? Option(string[] args, string name)
    {
        for (int i = 0; i < args.Length - 1; i++)
            if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
                return args[i + 1];
        return null;
    }

    private static (float r, float g, float b, float a) ParseColor(string text)
    {
        var parts = text.Split(',');
        if (parts.Length != 4)
            throw new Exception("--color expects exactly 4 comma separated floats: R,G,B,A");
        var v = new float[4];
        for (int i = 0; i < 4; i++)
        {
            if (!float.TryParse(parts[i], NumberStyles.Float, Inv, out v[i]))
                throw new Exception($"invalid color component #{i + 1}: '{parts[i]}'");
            if (v[i] < 0f || v[i] > 1f)
                throw new Exception($"color component #{i + 1} out of range 0..1: {v[i]}");
        }
        return (v[0], v[1], v[2], v[3]);
    }

    // The active branch of `flag ? Color(R,G,B,A) : Color(0,0,0,0)` is the
    // target of a brtrue.s. That branch target is a semantic anchor which
    // stays valid no matter what color was written previously, so the patcher
    // stays idempotent even after alpha is changed away from its stock 0.3.
    // The four instructions must be mutated in place: R is a branch target,
    // so replacing the Instruction objects would break the branch reference.
    private static Instruction[] LocateColorComponents(MethodDefinition onPreUpdate)
    {
        var branch = onPreUpdate.Body.Instructions.FirstOrDefault(i =>
            (i.OpCode == OpCodes.Brtrue_S || i.OpCode == OpCodes.Brtrue) &&
            i.Operand is Instruction t && t.OpCode == OpCodes.Ldc_R4)
            ?? throw new Exception("sensor active-branch (brtrue -> ldc.r4) not found in OnPreUpdate");

        var r = (Instruction)branch.Operand;
        var g = r.Next ?? throw new Exception("sensor G component not found");
        var b = g.Next ?? throw new Exception("sensor B component not found");
        var a = b.Next ?? throw new Exception("sensor A component not found");
        var all = new[] { r, g, b, a };
        foreach (var i in all)
            if (i.OpCode != OpCodes.Ldc_R4 || i.Operand is not float)
                throw new Exception($"unexpected sensor color instruction: {i}");

        if (a.Next is null || a.Next.OpCode != OpCodes.Newobj ||
            a.Next.Operand is not MethodReference ctor ||
            ctor.DeclaringType.Name != "Color" || ctor.Parameters.Count != 4)
            throw new Exception("sensor Color::.ctor not found directly after the four components");

        return all;
    }

    private static string F(Instruction i) =>
        ((float)i.Operand!).ToString("R", Inv);

    private static int Run(string[] args)
    {
        if (args.Length < 1) { Usage(); return 2; }

        string input = args[0];
        bool inspect = args.Any(a => string.Equals(a, "--inspect", StringComparison.OrdinalIgnoreCase));
        string? colorText = Option(args, "--color");
        string? output = (args.Length >= 2 && !args[1].StartsWith("--", StringComparison.Ordinal))
            ? args[1] : null;

        var asm = AssemblyDefinition.ReadAssembly(input, new ReaderParameters
        {
            ReadSymbols = false,
            InMemory = true
        });
        var module = asm.MainModule;

        var renderer = module.GetType("MajdataPlay.DummyTouchPanelRenderer")
                       ?? throw new Exception("DummyTouchPanelRenderer type not found (unsupported game version?)");
        var onPreUpdate = renderer.Methods.FirstOrDefault(m => m.Name == "OnPreUpdate")
                          ?? throw new Exception("OnPreUpdate not found (unsupported game version?)");

        // --inspect doubles as the compatibility check: it must be able to
        // locate the exact color IL before anything is written.
        var comps = LocateColorComponents(onPreUpdate);

        if (inspect)
        {
            Console.WriteLine(
                "{\"r\":" + F(comps[0]) +
                ",\"g\":" + F(comps[1]) +
                ",\"b\":" + F(comps[2]) +
                ",\"a\":" + F(comps[3]) + "}");
            return 0;
        }

        if (output is null) { Usage(); return 2; }
        var color = colorText is null ? (1f, 0f, 0f, 0.3f) : ParseColor(colorText);

        // Mutate Operand in place: the R instruction is a brtrue.s target.
        comps[0].Operand = color.Item1;
        comps[1].Operand = color.Item2;
        comps[2].Operand = color.Item3;
        comps[3].Operand = color.Item4;

        asm.Write(output, new WriterParameters { WriteSymbols = false });
        Console.WriteLine(
            "OK color=" + color.Item1.ToString("R", Inv) + "," +
            color.Item2.ToString("R", Inv) + "," +
            color.Item3.ToString("R", Inv) + "," +
            color.Item4.ToString("R", Inv));
        return 0;
    }
}
