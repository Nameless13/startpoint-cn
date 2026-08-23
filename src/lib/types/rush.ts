import { UserRushEventPlayedParty } from "../../data/types"
import { Reward } from "./rewards"

export enum RushEventFolder {
    NONE,
    INTERMEDIATE,
    ADVANCED,
    GODLY,
    ENDLESS
}


export type RushEventFolders = Record<string, Record<string, Reward[]>>

export type SerializedPlayerRushEventPlayedPartyList = Record<number, UserRushEventPlayedParty>

export interface SerializedPlayerRushEventPlayedParties {
    folderParties: SerializedPlayerRushEventPlayedPartyList
    endlessParties: SerializedPlayerRushEventPlayedPartyList
}

