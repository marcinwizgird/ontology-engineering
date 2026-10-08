/*
 * Semantic Intelligence Platform -- DEVELOPMENT VIEWPOINT.
 * SysML v2 textual notation.
 *
 * Module structure of src/Semantic Intelligence Platform/semantic_intelligence and the
 * layering rule tools/sysml_check.py and the test-suite enforce: a module may depend only
 * on modules of a lower layer (core < governance < domain services < platform < agents
 * < api). The agent layer depending on the platform -- never the reverse, and never on
 * core.changes or core.store directly -- is the code-level form of guarantee 2 in
 * SipFunctional.
 */

package SipDevelopment {

    private import ScalarValues::*;

    part def Module {
        attribute path : String;
        attribute layer : Integer;
        attribute linesOfCode : Integer[0..1];
    }

    part def CoreModule :> Module { doc /* core: layout, store, changes, events, principal, namespaces */ }
    part def GovernanceModule :> Module { doc /* governance: capabilities, registry(PDP), settings, urigen */ }
    part def OwlModule :> Module { doc /* owl: model, manchester, rendering, hierarchy, frames, refactor */ }
    part def SkosModule :> Module { doc /* skos */ }
    part def ReasoningModule :> Module { doc /* reasoning: reasoner, explanation */ }
    part def QualityModule :> Module { doc /* quality: icv, metrics, cq */ }
    part def SearchModule :> Module { doc /* search */ }
    part def AlignmentModule :> Module { doc /* alignment */ }
    part def IoModule :> Module { doc /* io: pipeline */ }
    part def KgModule :> Module { doc /* kg: lifting */ }
    part def PlatformModule :> Module { doc /* platform.py: operation registry */ }
    part def AgentsModule :> Module { doc /* agents: llm, base, specialists, simulators, orchestrator */ }
    part def ApiModule :> Module { doc /* api: FastAPI app */ }
    part def TestsModule :> Module { doc /* tests: pytest suite incl. architecture rules and the FIBO corpus regression */ }

    part codebase {
        part core : CoreModule { :>> path = "core"; :>> layer = 0; }
        part governance : GovernanceModule { :>> path = "governance"; :>> layer = 1; }
        part owl : OwlModule { :>> path = "owl"; :>> layer = 2; }
        part skos : SkosModule { :>> path = "skos"; :>> layer = 2; }
        part reasoning : ReasoningModule { :>> path = "reasoning"; :>> layer = 2; }
        part quality : QualityModule { :>> path = "quality"; :>> layer = 2; }
        part search : SearchModule { :>> path = "search"; :>> layer = 2; }
        part alignment : AlignmentModule { :>> path = "alignment"; :>> layer = 2; }
        part io : IoModule { :>> path = "io"; :>> layer = 2; }
        part kg : KgModule { :>> path = "kg"; :>> layer = 2; }
        part platform : PlatformModule { :>> path = "platform.py"; :>> layer = 3; }
        part agents : AgentsModule { :>> path = "agents"; :>> layer = 4; }
        part api : ApiModule { :>> path = "api"; :>> layer = 5; }
        part tests : TestsModule { :>> path = "tests"; :>> layer = 6; }
    }

    dependency governanceOnCore from codebase.governance to codebase.core;
    dependency owlOnCore from codebase.owl to codebase.core;
    dependency skosOnCore from codebase.skos to codebase.core;
    dependency reasoningOnOwl from codebase.reasoning to codebase.owl;
    dependency qualityOnOwl from codebase.quality to codebase.owl;
    dependency platformOnServices from codebase.platform to codebase.owl, codebase.skos,
        codebase.reasoning, codebase.quality, codebase.search, codebase.alignment,
        codebase.io, codebase.kg, codebase.governance, codebase.core;
    dependency agentsOnPlatform from codebase.agents to codebase.platform;
    dependency apiOnPlatform from codebase.api to codebase.platform, codebase.agents;

    constraint def LayeringRule {
        doc /* for every import a -> b inside the package: layer(a) >= layer(b), and
             * agents never import core.changes or core.store. Checked by
             * tests/test_architecture.py on the real import graph. */
    }
}
